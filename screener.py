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
    """KRX 전체 종목 리스트 수집 (FinanceDataReader 활용)"""
    try:
        df = fdr.StockListing('KRX')
        df = df[df['Market'].isin(['KOSPI', 'KOSDAQ'])]
        df = df[~df['Name'].str.contains('스팩|우|ETN|ETF', na=False)]
        
        tickers = []
        for _, row in df.iterrows():
            code = str(row['Code']).zfill(6)
            suffix = '.KS' if row['Market'] == 'KOSPI' else '.KQ'
            tickers.append((code + suffix, row['Name']))
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

def check_minervini_template(symbol, name, df_bench):
    """미너비니 트렌드 템플릿 조건 검증"""
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

        cond1 = close > sma150 and close > sma200
        cond2 = sma150 > sma200
        cond3 = sma200 > sma200_20d_ago
        cond4 = sma50 > sma150 and sma50 > sma200
        cond5 = close > sma50
        cond6 = close >= (low_52wk * 1.30)
        cond7 = close >= (high_52wk * 0.75)

        if all([cond1, cond2, cond3, cond4, cond5, cond6, cond7]):
            rs_score = calculate_rs(df, df_bench)
            pct_from_high = round(((close - high_52wk) / high_52wk) * 100, 2)
            pct_from_low = round(((close - low_52wk) / low_52wk) * 100, 2)
            
            return {
                '종목명': name,
                '티커': symbol,
                '현재가': round(close, 2),
                'RS점수': rs_score,
                '고점대비(%)': pct_from_high,
                '저점대비(%)': pct_from_low
            }
    except Exception:
        return None
    return None

def send_email(df_res):
    """지정된 이메일로 리스트 메일 발송"""
    sender_email = "dueoghks@gmail.com"
    receiver_email = "dueoghks@gmail.com"
    app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not app_password:
        print("이메일 발송 실패: GMAIL_APP_PASSWORD 환경변수가 설정되지 않았증니다.")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"[미너비니 스크리너] {today_str} 주도주 발굴 목록 (총 {len(df_res)}종목)"

    # HTML 표 디자인 및 본문 생성
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
        <p>오늘 조건검색에 포착된 상승 2단계 주도주 후보는 총 <b>{len(df_res)}개</b>입니다.</p>
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
    print("=== 미너비니 스크리너 실행 ===")
    tickers = get_krx_tickers()
    bench = yf.Ticker("^KS11").history(period="1y")
    
    results = []
    print(f"총 {len(tickers)}개 종목 스크리닝 중...")
    
    for symbol, name in tickers:
        res = check_minervini_template(symbol, name, bench)
        if res:
            results.append(res)
            print(f"[발굴] {name} ({symbol}) | RS 점수: {res['RS점수']}")
            
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        # RS 점수 기준 내림차순 정렬
        df_res = df_res.sort_values(by='RS점수', ascending=False)
        print(f"\n스크리닝 완료! 총 {len(df_res)}개 발굴. 메일 발송을 시작합니다.")
        send_email(df_res)
    else:
        print("\n조건을 만족하는 종목이 없습니다.")

if __name__ == "__main__":
    main()
