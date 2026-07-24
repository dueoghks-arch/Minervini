import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import numpy as np
import yfinance as yf
import FinanceDataReader as fdr

def get_krx_tickers():
    """KRX 전체 종목 중 시가총액 3,000억 원 이상 종목만 수집"""
    try:
        df = fdr.StockListing('KRX')
        
        # 1. KOSPI / KOSDAQ 대상 (스팩, 우선주, ETN, ETF 제외)
        df = df[df['Market'].isin(['KOSPI', 'KOSDAQ'])]
        df = df[~df['Name'].str.contains('스팩|우|ETN|ETF', na=False)]
        
        # 2. [신규 조건] 시가총액 3,000억 원 이상 (Marcap 단위: 원)
        # 3,000억 원 = 300,000,000,000
        min_marcap = 300_000_000_000
        if 'Marcap' in df.columns:
            df = df[df['Marcap'] >= min_marcap]
        
        tickers = []
        for _, row in df.iterrows():
            code = str(row['Code']).zfill(6)
            suffix = '.KS' if row['Market'] == 'KOSPI' else '.KQ'
            
            # 시가총액(억 원 단위 표기용)
            marcap_billion = int(row['Marcap'] / 100_000_000) if 'Marcap' in df.columns else 0
            
            tickers.append({
                'symbol': code + suffix,
                'name': row['Name'],
                'marcap': marcap_billion
            })
        return tickers
    except Exception as e:
        print(f"티커 수집 중 오류 발생: {e}")
        return []

def calculate_rs(df_stock, df_bench):
    """지수 대비 상대강도(RS) 점수 산출"""
    try:
        stock_3m = (df_stock['Close'].iloc[-1] / df_stock['Close'].iloc[-63]) - 1
        stock_6m = (df_stock['Close'].iloc[-1] / df_stock['Close'].iloc[-126]) - 1
        bench_3m = (df_bench['Close'].iloc[-1] / df_bench['Close'].iloc[-63]) - 1
        bench_6m = (df_bench['Close'].iloc[-1] / df_bench['Close'].iloc[-126]) - 1
        
        rs_score = ((stock_3m - bench_3m) * 0.4) + ((stock_6m - bench_6m) * 0.6)
        return round(rs_score * 100, 2)
    except:
        return 0.0

def check_minervini_template(ticker_info, df_bench):
    """미너비니 트렌드 템플릿 조건 검증 (AND 조건 결합)"""
    symbol = ticker_info['symbol']
    name = ticker_info['name']
    marcap = ticker_info['marcap']
    
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period="1y")
        
        if len(df) < 200:
            return None

        close = df['Close'].iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma150 = df['Close'].rolling(150).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        sma200_20d_ago = df['Close'].rolling(200).mean().iloc[-20]

        low_52wk = df['Close'].min()
        high_52wk = df['Close'].max()

        # --- [미너비니 7대 기술적 조건] ---
        cond1 = close > sma150 and close > sma200
        cond2 = sma150 > sma200
        cond3 = sma200 > sma200_20d_ago
        cond4 = sma50 > sma150 and sma50 > sma200
        cond5 = close > sma50
        cond6 = close >= (low_52wk * 1.30)
        cond7 = close >= (high_52wk * 0.75)

        # 기본 기술적 조건 통과 여부
        is_minervini_trend = all([cond1, cond2, cond3, cond4, cond5, cond6, cond7])

        if is_minervini_trend:
            rs_score = calculate_rs(df, df_bench)
            
            # --- [추가 필터링 AND 조건] ---
            # 1. RS 점수 70점 이상 (주도주급 강세)
            cond_rs = rs_score >= 70.0
            
            # 2. 최근 20일 평균 거래대금 20억원 이상 (유동성 확보)
            avg_trading_val_20d = (df['Volume'] * df['Close']).tail(20).mean()
            cond_volume = avg_trading_val_20d >= 2_000_000_000

            # 모든 AND 조건 충족 시 최종 발굴
            if cond_rs and cond_volume:
                pct_from_high = round(((close - high_52wk) / high_52wk) * 100, 2)
                pct_from_low = round(((close - low_52wk) / low_52wk) * 100, 2)
                
                return {
                    '종목명': name,
                    '티커': symbol,
                    '현재가': round(close, 2),
                    '시가총액(억)': marcap,
                    'RS점수': rs_score,
                    '고점대비(%)': pct_from_high,
                    '저점대비(%)': pct_from_low
                }
    except Exception:
        return None
    return None

def send_email(df_res):
    """지정된 이메일로 리스트 메일 발송"""
    sender_email = os.environ.get("EMAIL_USER")
    receiver_email = os.environ.get("EMAIL_USER")
    app_password = os.environ.get("EMAIL_PASS")

    if not app_password or not sender_email:
        print("이메일 발송 실패: EMAIL_USER 또는 EMAIL_PASS 환경변수가 설정되지 않았습니다.")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"[미너비니 스크리너] {today_str} 엄선 주도주 목록 (총 {len(df_res)}종목)"

    table_html = df_res.to_html(index=False, justify='center', border=1)
    
    html_body = f"""
    <html>
    <head>
        <style>
            table {{ border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; }}
            th {{ background-color: #1e3a8a; color: white; padding: 8px; text-align: center; }}
            td {{ padding: 8px; text-align: center; border-bottom: 1px solid #ddd; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h2>미너비니 트렌드 템플릿 검색 결과 ({today_str})</h2>
        <p><b>적용된 AND 조건:</b></p>
        <ul>
            <li>미너비니 트렌드 템플릿 (상승 2단계) 조건 만족</li>
            <li><b>시가총액 3,000억 원 이상</b></li>
            <li><b>RS 점수 70점 이상</b></li>
            <li><b>최근 20일 평균 거래대금 20억 원 이상</b></li>
        </ul>
        <p>오늘 조건검색에 포착된 주도주 후보는 총 <b>{len(df_res)}개</b>입니다.</p>
        {table_html}
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print("이메일 발송 성공!")
    except Exception as e:
        print(f"이메일 발송 오류: {e}")

def main():
    print("=== 미너비니 스크리너 실행 (시총 3,000억 이상 필터 적용) ===")
    tickers = get_krx_tickers()
    bench = yf.Ticker("^KS11").history(period="1y")
    
    results = []
    print(f"시가총액 3,000억 이상 대상 종목: 총 {len(tickers)}개 스크리닝 중...")
    
    for ticker_info in tickers:
        res = check_minervini_template(ticker_info, bench)
        if res:
            results.append(res)
            print(f"[발굴] {res['종목명']} ({res['티커']}) | 시총: {res['시가총액(억)']}억 | RS: {res['RS점수']}")
            
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res = df_res.sort_values(by='RS점수', ascending=False)
        print(f"\n스크리닝 완료! 총 {len(df_res)}개 최종 발굴. 메일 발송을 시작합니다.")
        send_email(df_res)
    else:
        print("\n조건을 만족하는 종목이 없습니다.")

if __name__ == "__main__":
    main()
