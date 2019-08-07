from urllib.parse import urlencode
from urllib.request import urlopen
from datetime import datetime
from parameters import ticker2finam
from multiprocessing import Pool
from tqdm import tqdm
from itertools import repeat
from datetime import timedelta
import numpy as np
from scipy.signal import argrelextrema
from scipy.signal import savgol_filter
from tqdm import tqdm
import os
import pandas as pd
import itertools
import time


def load_single(ticker, data_prefix, start_date, end_date, period=3):        
    FINAM_URL = "http://export.finam.ru/"# сервер, на который стучимся
    market = 0 #можно не задавать. Это рынок, на котором торгуется бумага. Для акций работает с любой цифрой. Другие рынки не проверял.
    #Делаем преобразования дат:
    #start_date = datetime.strptime(start, "%d.%m.%Y").date()
    start_date_rev=start_date.strftime('%Y%m%d')
    #end_date = datetime.strptime(end, "%d.%m.%Y").date()
    end_date_rev=end_date.strftime('%Y%m%d')


    #Все параметры упаковываем в единую структуру. Здесь есть дополнительные параметры, кроме тех, которые заданы в шапке. См. комментарии внизу:
    params = urlencode([
                        ('market', market), #на каком рынке торгуется бумага
                        ('em', ticker2finam[ticker]), #вытягиваем цифровой символ, который соответствует бумаге.
                        ('code', ticker), #тикер нашей акции
                        ('apply',0), #не нашёл что это значит. 
                        ('df', start_date.day), #Начальная дата, номер дня (1-31)
                        ('mf', start_date.month - 1), #Начальная дата, номер месяца (0-11)
                        ('yf', start_date.year), #Начальная дата, год
                        ('from', start_date), #Начальная дата полностью
                        ('dt', end_date.day), #Конечная дата, номер дня	
                        ('mt', end_date.month - 1), #Конечная дата, номер месяца
                        ('yt', end_date.year), #Конечная дата, год
                        ('to', end_date), #Конечная дата
                        ('p', period), #Таймфрейм
                        ('f', ticker+"_" + start_date_rev + "_" + end_date_rev), #Имя сформированного файла
                        ('e', ".csv"), #Расширение сформированного файла
                        ('cn', ticker), #ещё раз тикер акции	
                        ('dtf', 1), #В каком формате брать даты. Выбор из 5 возможных. См. страницу https://www.finam.ru/profile/moex-akcii/sberbank/export/
                        ('tmf', 1), #В каком формате брать время. Выбор из 4 возможных.
                        ('MSOR', 0), #Время свечи (0 - open; 1 - close)	
                        ('mstime', "on"), #Московское время	
                        ('mstimever', 1), #Коррекция часового пояса	
                        ('sep', 1), #Разделитель полей	(1 - запятая, 2 - точка, 3 - точка с запятой, 4 - табуляция, 5 - пробел)
                        ('sep2', 1), #Разделитель разрядов
                        ('datf', 1), #Формат записи в файл. Выбор из 6 возможных.
                        ('at', 1)]) #Нужны ли заголовки столбцов
    url = FINAM_URL + ticker+"_" + start_date_rev + "_" + end_date_rev + ".csv?" + params #урл составлен!
    txt=urlopen(url).readlines() #здесь лежит огромный массив данных, прилетевший с Финама.
    local_file = open('{}/{}.csv'.format(data_prefix, ticker), "w") #задаём файл, в который запишем котировки.
    for line in txt: #записываем свечи строку за строкой. 
        local_file.write(line.strip().decode( "utf-8" )+'\n')
    local_file.close()
    
    
    
def load_tickers(data_prefix, tickers, start_date, end_date, period=3):
    for ticker in tqdm(tickers):
        try:
            load_single(ticker, data_prefix, start_date, end_date, period)
            time.sleep(0.6)
        except:
            print(ticker)
    
    
# def load_update_today(data_prefix, tickers):
#     for ticker in tqdm(tickers):
#         try:
#             load_single(ticker, data_prefix, start_date, end_date, period)    
    
    
def load_dfs(dir_path, tickers):
    ticker2df = {}
    for ticker in tickers:
        try:
            df = pd.read_csv('{}/{}.csv'.format(dir_path, ticker))
            df['date'] = df['<DATE>'].apply(lambda x: datetime.strptime(str(x), "%Y%m%d").date())
            if df.shape[0] < 300:
                continue

            #if df['date'].max() < datetime.strptime("20190501", "%Y%m%d").date():
            #    continue

            ticker2df[ticker] = df
        except:
            print(ticker)

    return ticker2df



def single_sample(df, corn_date, test_mode):
    feats, target_vals = None, None
    target_df = df_between(df, corn_date, corn_date + timedelta(days=1))
    
    last_df = df_between(df, start_date=None, end_date=corn_date)
    close_price = last_df['<CLOSE>'].values[-1]
    
    if len(target_df) > 0 or test_mode:
        feats = calc_feat(df, target_df, corn_date)
        target_vals = np.array([close_price] + list(target_df['<OPEN>'].values))

            
        #target = (target_vals[-1] - target_vals[0]) / target_vals[0] > 0.


    return feats, target_vals

    
def single_ticker(ticker_df, corn_date, test_mode):
    ticker_feats, ticker_targets = [], []
    for date in corn_date:
        f, t = single_sample(ticker_df, date, test_mode)
        if f is not None:
            ticker_feats.append(f)
            ticker_targets.append(t)

    if len(ticker_feats) > 0:
        ticker_feats = pd.concat(ticker_feats, axis=0)
        if not test_mode:
            ticker_targets = np.array(ticker_targets)

    return ticker_feats, ticker_targets


def all_samples(ticker2df, dates, test_mode=False):
    p = Pool(20)
    feats_res = []
    y_res = []
    #res = p.starmap(self.single_sample, itertools.product(tickers, dates))
    res = p.starmap(single_ticker, zip(ticker2df.values(), repeat(dates), repeat(test_mode)))

    #return res
    for feat, y in res:
        if len(feat) > 0:
            feats_res.append(feat)
            y_res.append(y)

    feats_res = pd.concat(feats_res, axis=0)
    feats_res.index = range(len(feats_res))
    #feats_res = np.concatenate(feats_res, axis=0)
    #y_res = np.concatenate(y_res, axis=0)

    return feats_res, y_res    

        
        



def df_between(df, start_date=None, end_date=None):
    mask = np.ones(len(df), dtype=bool)
    if start_date is not None:
        mask_start = df['date'].apply(lambda x: x >= start_date).values
        mask = mask * mask_start
    if end_date is not None:
        mask_end = df['date'].apply(lambda x: x < end_date).values
        mask = mask * mask_end

    return df.loc[mask]


def calc_base_time_features(series):
    if len(series) == 0:
        series = np.array([np.nan])
        
    feats = [series.std() / series.max(),
             series.mean() / series.max(),
             series.min() / series.max(),
             np.median(series) / series.max(),
             (series.max() - series.min()) / series.max(),
             (series[-1] - series[0]) / series.max()
            ]
    
    #col_names = 
    
    return feats#, col_names


def calc_support_features(series):
    if len(series) == 0:
        series = np.array([np.nan])
        
    support_levels = calc_support_levels(series)
    
    if len(support_levels) == 0:
        support_levels = np.array([np.nan])
        
    
    support_diff = series[-1] - support_levels

    upper_supports = support_levels[support_diff < 0]
    lower_supports = support_levels[support_diff > 0]
    
    if len(upper_supports) == 0:
        upper_supports = np.array([np.nan])        
        
    if len(lower_supports) == 0:
        lower_supports = np.array([np.nan])        
            
    if len(series) == 0:
        series = np.array([np.nan])


        
        
    upper_supports_diff = np.abs(upper_supports - series[-1])
    lower_supports_diff = np.abs(lower_supports - series[-1])
   
    support_features = [len(upper_supports[~np.isnan(upper_supports)]),
                        len(lower_supports[~np.isnan(lower_supports)]),
                        upper_supports.min() / series.max(),
                        lower_supports.max() / series.max(),
                        support_levels.max() / series.max(),
                        support_levels.min() / series.max(),
                        upper_supports_diff.min() / series.max(),
                        lower_supports_diff.min() / series.max()]
    
    
    return support_features
    
    

def calc_feat(df, target_df, corn_date):
    ticker = df['<TICKER>'].values[0] 
        
    month_series = df_between(df, corn_date - timedelta(days=31), corn_date)['<OPEN>'].values
    week_series = df_between(df, corn_date - timedelta(days=7), corn_date)['<OPEN>'].values
    
    day3_df = df_between(df, start_date=None, end_date=corn_date)
    day3_df = df_last(day3_df, 3)
    day3_series = day3_df['<OPEN>'].values
    
    if len(target_df) > 0:
        start_val = target_df['<OPEN>'].values[0]
        next_day_feat = [(day3_series[-1] - start_val) / day3_series[-1]]
    else:
        next_day_feat = [np.nan]
    
    month_feats = calc_base_time_features(month_series)
    week_feats = calc_base_time_features(week_series)
    day3_feats = calc_base_time_features(day3_series)    
    
    
    intoday_base_features = []
    for date in day3_df['date'].unique():
        intoday_base_features.append(calc_base_time_features(day3_df[day3_df['date'] == date]['<OPEN>'].values))
        
    intoday_base_features = np.array(intoday_base_features).flatten()
    
    
    support_features = calc_support_features(month_series)
    
    close_price = [day3_df['<CLOSE>'].values[-1]]
    
    result = np.concatenate([month_feats, week_feats, day3_feats, intoday_base_features, support_features, close_price, next_day_feat], axis=0)
    result = np.expand_dims(result, axis=0)
    result = pd.DataFrame(result)
    
    result['ticker'] = ticker
    result['corn_date'] = corn_date
    
    return result


def get_month_series(df, corn_date):
    month_series = df_between(df, corn_date - timedelta(days=31), corn_date)['<OPEN>'].values
    return month_series
    


def df_last(df, day_cnt):
    dates = np.sort(df['date'].unique())[-day_cnt:]
    start_date = dates[0]
    end_date = dates[-1] + timedelta(days=1)
    return df_between(df, start_date, end_date)

        
def calc_support_levels(series):
    if len(series) < 2:
        return []
    line_cnts = []
    line_vals = np.linspace(series.min(), series.max(), 100)
    for line in line_vals:
        line_cnts.append((np.abs(series - line) / series.max() < 0.001).sum())

    sm_line_cnts = savgol_filter(line_cnts, 11, 3)
    loc_maximum_idxs = argrelextrema(sm_line_cnts, np.greater)[0]
    loc_maximums = line_vals[loc_maximum_idxs]
    
    return loc_maximums




















        
        
        
        
        