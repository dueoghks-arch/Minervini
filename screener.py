import os
import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import FinanceDataReader as fdr

def get_krx_tickers():
    """KRX 전체 종목 리스트 수집 (FinanceDataReader 활용)"""
    try:
        df = fdr.StockListing('KRX')
        # KOSPI / KOSDAQ 대상 (스팩, 우선주, ETF 제외)
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
        
        # 최근 3개월 및 6개월 상대 수익률 가중합
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

        # 미너비니 8대 조건
        cond1 = close > sma150 and close > sma200       # 현재가 > 150일선, 200일선
        cond2 = sma150 > sma200                         # 150일선 > 200일선
        cond3 = sma200 > sma200_20d_ago                 # 200일선 우상향 (최소 20일 이상)
        cond4 = sma50 > sma150 and sma50 > sma200       # 50일선 > 150일선, 200일선
        cond5 = close > sma50                           # 현재가 > 50일선
        cond6 = close >= (low_52wk * 1.30)              # 52주 저점 대비 +30% 이상 상승
        cond7 = close >= (high_52wk * 0.75)             # 52주 고점 대비 -25% 이내 위치

        if all([cond1, cond2, cond3, cond4, cond5, cond6, cond7]):
            rs_score = calculate_rs(df, df_bench)
            pct_from_high = round(((close - high_52wk) / high_52wk) * 100, 2)
            pct_from_low = round(((close - low_52wk) / low_52wk) * 100, 2)
            
            return {
                'Symbol': symbol,
                'Name': name,
                'Close': round(close, 2),
                'RS_Score': rs_score,
                'From_High_%': pct_from_high,
                'From_Low_%': pct_from_low
            }
    except Exception:
        return None
    return None

def main():
    print("=== 미너비니 스크리너 실행 ===")
    tickers = get_krx_tickers()
    
    # 벤치마크 (코스피 지수)
    bench = yf.Ticker("^KS11").history(period="1y")
    
    results = []
    print(f"총 {len(tickers)}개 종목 스크리닝 중...")
    
    for symbol, name in tickers:
        res = check_minervini_template(symbol, name, bench)
        if res:
            results.append(res)
            print(f"[발굴] {name} ({symbol}) | RS 점수: {res['RS_Score']}")
            
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res = df_res.sort_values(by='RS_Score', ascending=False)
        df_res.to_csv("minervini_candidates.csv", index=False, encoding='utf-8-sig')
        print(f"\n스크리닝 완료! 총 {len(df_res)}개 주도주 후보 발굴 완료.")
    else:
        print("\n조건을 만족하는 종목이 없습니다.")

if __name__ == "__main__":
    main()
