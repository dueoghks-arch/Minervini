import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import numpy as np
import yfinance as yf

import io
import urllib.request
import pandas as pd

def get_us_tickers():
    """S&P 500 및 NASDAQ 100 티커 수집 (User-Agent 및 io.StringIO 적용)"""
    tickers = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    # 1. S&P 500 수집
    try:
        sp500_url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        req = urllib.request.Request(sp500_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
        
        sp500_table = pd.read_html(io.StringIO(html))[0]
        sp500_tickers = sp500_table['Symbol'].str.replace('.', '-', regex=False).tolist()
        tickers.update(sp500_tickers)
        print(f"S&P 500 수집 완료: {len(sp500_tickers)}개")
    except Exception as e:
        print(f"S&P 500 수집 실패: {e}")

    # 2. NASDAQ 100 수집
    try:
        nasdaq100_url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        req = urllib.request.Request(nasdaq100_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            
        nasdaq100_tables = pd.read_html(io.StringIO(html))
        
        nasdaq_table = None
        for t in nasdaq100_tables:
            if 'Ticker' in t.columns or 'Symbol' in t.columns:
                nasdaq_table = t
                break
        
        if nasdaq_table is not None:
            col_name = 'Ticker' if 'Ticker' in nasdaq_table.columns else 'Symbol'
            nasdaq_tickers = nasdaq_table[col_name].str.replace('.', '-', regex=False).tolist()
            tickers.update(nasdaq_tickers)
            print(f"NASDAQ 100 수집 완료 (중복제거 전): {len(nasdaq_tickers)}개")
    except Exception as e:
        print(f"NASDAQ 100 수집 실패: {e}")

    final_tickers = list(tickers)
    print(f"➔ 통합 최종 대상 종목 수: {len(final_tickers)}개")
    return final_tickers

def calculate_rs(df_stock, df_bench):
    """S&P 500 지수(^GSPC) 대비 RS 점수 산출"""
    try:
        stock_3m = (df_stock['Close'].iloc[-1] / df_stock['Close'].iloc[-63]) - 1
        stock_6m = (df_stock['Close'].iloc[-1] / df_stock['Close'].iloc[-126]) - 1
        bench_3m = (df_bench['Close'].iloc[-1] / df_bench['Close'].iloc[-63]) - 1
        bench_6m = (df_bench['Close'].iloc[-1] / df_bench['Close'].iloc[-126]) - 1
        
        rs_score = ((stock_3m - bench_3m) * 0.4) + ((stock_6m - bench_6m) * 0.6)
        return round(rs_score * 100, 2)
    except:
        return 0.0

def check_minervini_us(symbol, df_bench):
    """미국주식 미너비니 조건 및 필터 검증"""
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

        # 미너비니 7대 기술적 조건
        cond1 = close > sma150 and close > sma200
        cond2 = sma150 > sma200
        cond3 = sma200 > sma200_20d_ago
        cond4 = sma50 > sma150 and sma50 > sma200
        cond5 = close > sma50
        cond6 = close >= (low_52wk * 1.30)
        cond7 = close >= (high_52wk * 0.75)

        if all([cond1, cond2, cond3, cond4, cond5, cond6, cond7]):
            rs_score = calculate_rs(df, df_bench)
            
            # [미국장 필터 조건]
            # 1. RS 점수 70점 이상
            # 2. 최근 20일 평균 거래대금 $1,000만 달러(약 130억 원) 이상
            avg_trading_val = (df['Volume'] * df['Close']).tail(20).mean()
            
            if rs_score >= 70.0 and avg_trading_val >= 10_000_000:
                pct_from_high = round(((close - high_52wk) / high_52wk) * 100, 2)
                pct_from_low = round(((close - low_52wk) / low_52wk) * 100, 2)
                
                # 풀네임 가져오기
                company_name = stock.info.get('shortName', symbol)
                
                return {
                    '티커': symbol,
                    '종목명': company_name,
                    '현재가($)': round(close, 2),
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
    msg['Subject'] = f"[미너비니 US 스크리너] {today_str} 미국 주도주 발굴 목록 (총 {len(df_res)}종목)"

    table_html = df_res.to_html(index=False, justify='center', border=1)
    
    html_body = f"""
    <html>
    <head>
        <style>
            table {{ border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; }}
            th {{ background-color: #0f172a; color: white; padding: 8px; text-align: center; }}
            td {{ padding: 8px; text-align: center; border-bottom: 1px solid #ddd; }}
            tr:nth-child(even) {{ background-color: #f8fafc; }}
        </style>
    </head>
    <body>
        <h2>미국주식(S&P500 + NASDAQ100) 미너비니 스크리닝 결과 ({today_str})</h2>
        <p><b>적용 조건:</b> 상승 2단계 트렌드 + RS점수 70점 이상 + 일평균 거래대금 $1,000만 이상</p>
        <p>오늘 조건검색에 포착된 종목은 총 <b>{len(df_res)}개</b>입니다.</p>
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
    print("=== 미국주식(S&P500 + NASDAQ100) 스크리너 시작 ===")
    tickers = get_us_tickers()
    bench = yf.Ticker("^GSPC").history(period="1y") # S&P 500 지수
    
    results = []
    print("스크리닝 진행 중...")
    
    for symbol in tickers:
        res = check_minervini_us(symbol, bench)
        if res:
            results.append(res)
            print(f"[발굴] {res['티커']} ({res['종목명']}) | RS: {res['RS점수']}")
            
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res = df_res.sort_values(by='RS점수', ascending=False)
        print(f"\n스크리닝 완료! 총 {len(df_res)}개 발굴. 메일을 발송합니다.")
        send_email(df_res)
    else:
        print("\n조건을 만족하는 종목이 없습니다.")

if __name__ == "__main__":
    main()
