import argparse
from datetime import timedelta
import logging
import time
import pandas as pd
from config import load_config

from exchanges import exchange
from download import download_candles
import plotly.graph_objects as go
from dash import Dash, State, dcc, html, Input, Output
import talib
from plotly.subplots import make_subplots


# candle data
chardata = {}
chart_max_size = 2000
chart_display_size = 200
# 图表更新间隔（s）
graph_update_interval = 5
# 图表最后更新时间 timestamp
graph_update_timestamp = 0.0



app = Dash(__name__)

app.layout = html.Div([
    dcc.Dropdown(['NEAR/USDT:USDT', 'BTC/USDT:USDT', 'ETH/USDT:USDT'], 'NEAR/USDT:USDT', id='symbol'),
    dcc.Interval(id='update', interval=graph_update_interval*1000, n_intervals=0),
    dcc.Graph(id="graph",
        config={
            'scrollZoom': True,  # 启用或禁用滚动缩放
        }
    ),
])

pd.set_option('display.max_rows', 10)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')


def get_chart(ex, symbol, timeframe, limit):
    ohlcv = download_candles(ex, symbol, timeframe)
    df = pd.DataFrame(ohlcv, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['date'], unit='ms', utc=True).dt.tz_convert('Asia/Shanghai')
    # get last some rows
    df = df.tail(limit).reset_index(drop=True)
    chardata[symbol] = df

# 绘制蜡烛图
def draw_fig_candle(df):
    fig =  go.Figure(data=[go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
    current_price = df['close'].iloc[-1]
    color = 'green' if current_price >= df['close'].iloc[-2] else 'red';
    fig.add_shape(
        type='line',
        y0=current_price, y1=current_price,
        x0=df['date'].iloc[0], x1=df['date'].iloc[-1]+timedelta(days=1),
        line=dict(
            color=color,
            width=1,
            dash='dash',
        ),
    )
    # 在Y轴上显示当前价格
    fig.add_annotation(
        xref='paper', yref='y',
        x=1.035, y=current_price,
        text="{:.4f}".format(current_price),
        showarrow=False,
        font=dict(
            size=12,
            color='White',
        ),
        bgcolor=color,
        bordercolor=color,
        borderwidth=1,
    )

    return fig
# 绘制MACD指标
def draw_fig_macd(df):
        close_prices = df['close'].values  # 获取收盘价的数据
        # 计算MACD指标
        # 设置参数
        fast_period = 12
        slow_period = 26
        signal_period = 9
        macd, signal, hist = talib.MACD(close_prices, fast_period, slow_period, signal_period)
        macd_y_min = min(hist[-chart_display_size:].min(), macd[-chart_display_size:].min(), signal[-chart_display_size:].min())
        macd_y_max = max(hist[-chart_display_size:].max(), macd[-chart_display_size:].max(), signal[-chart_display_size:].max())
        # 画MACD指标
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=macd,
            name='DIF',
            mode='lines',
            line=dict(color='orange', width=1),
            yaxis='y2',
        ))
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=signal,
            name='DEA',
            mode='lines',
            line=dict(color='blue', width=1),
            yaxis='y2',
        ))
        fig.add_trace(go.Bar(
            x=df['date'],
            y=hist,
            name='MACD',
            marker=dict(color='grey'),
            yaxis='y2',
        ))

        return fig, dict(range=[macd_y_min, macd_y_max])
# 绘制鼠标点击的垂直线
def draw_fig_with_click_data(fig, click_data, df, macd_yaxis_range):
    if click_data is not None:
        if 'x' in click_data['points'][0]:
            x = click_data['points'][0]['x']
            xdate = pd.to_datetime(x).tz_localize('Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S%z')
            shape = dict(
                type='line',
                x0=xdate, y0=min(macd_yaxis_range['range'][0], df['low'].min())*0.8,
                x1=xdate, y1=max(macd_yaxis_range['range'][1], df['high'].max())*1.2,
                line=dict(
                    color='black',
                    width=1,
                    dash='dash',
                )
            )
            fig.add_shape(shape, row=1, col=1)
            fig.add_shape(shape, row=2, col=1)

# 绘制鼠标悬停的垂直线
def draw_fig_with_hover_data(fig, hover_data, df, macd_yaxis_range):
    if hover_data is not None:
        if 'x' in hover_data['points'][0]:
            x = hover_data['points'][0]['x']
            xdate = pd.to_datetime(x).tz_localize('Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S%z')
            shape = dict(
                type='line',
                x0=xdate, y0=min(macd_yaxis_range['range'][0], df['low'].min())*0.8,
                x1=xdate, y1=max(macd_yaxis_range['range'][1], df['high'].max())*1.2,
                line=dict(
                    color='darkgrey',
                    width=1,
                    dash='dot',
                )
            )
            fig.add_shape(shape, row=1, col=1)
            fig.add_shape(shape, row=2, col=1)

def fig_relayout(fig,relayout_data):
    if relayout_data:
        layout = fig['layout']
        if 'xaxis.range[0]' in relayout_data:
            layout['xaxis']['range'] = [relayout_data['xaxis.range[0]'], relayout_data['xaxis.range[1]']]
        if 'xaxis2.range[0]' in relayout_data:
            layout['xaxis2']['range'] = [relayout_data['xaxis2.range[0]'], relayout_data['xaxis2.range[1]']]
        if 'yaxis.range[0]' in relayout_data:
            layout['yaxis']['range'] = [relayout_data['yaxis.range[0]'], relayout_data['yaxis.range[1]']]
        if 'yaxis2.range[0]' in relayout_data:
            layout['yaxis2']['range'] = [relayout_data['yaxis2.range[0]'], relayout_data['yaxis2.range[1]']]
        fig['layout'] = layout

def get_charting(symbol, timeframe):
        if symbol not in chardata:
            get_chart(ex, symbol, timeframe, chart_max_size)
        df = chardata[symbol] 
        # last_date_timestamp = int(df.iloc[-1]['date'].timestamp()*1000)
        last_date = df.iloc[-1]['date']
        # 只获取最新的蜡烛图，会导致最终的蜡烛图没更新到最新就切换到下一个蜡烛图了，造成数据不准确
        # 所以获取最后两根蜡烛图去修复上一根蜡烛图的数据
        global graph_update_timestamp
        current_timestamp = time.time()
        if round(current_timestamp - graph_update_timestamp) >= graph_update_interval:
            graph_update_timestamp = current_timestamp
            logging.debug(f"update candles: {symbol}, {graph_update_timestamp}")
            last_candles: list = ex.get_candles(symbol, timeframe, None, 2)
            #print(last_candles)
            current_candle: list = last_candles[-1]
            last_candle: list = last_candles[-2]

            current_candle[0] = pd.Timestamp(current_candle[0], unit='ms', tz='Asia/Shanghai')
            last_candle[0] = pd.Timestamp(last_candle[0], unit='ms', tz='Asia/Shanghai')
            
            if last_date == current_candle[0]:
                df.iloc[-1] = current_candle
            elif last_date < current_candle[0]: 
                df.loc[len(df)] = current_candle
                # 添加新的蜡烛图后，需要把上一根蜡烛图的数据修复
                df.iloc[-2] = last_candle
        return df


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='exbot for python')
    parser.add_argument('-c', '--config', type=str, required=True, help='config file path')
    # parser.add_argument('--symbol', type=str, required=True, help='The trading symbol to use')
    parser.add_argument('-t', '--timeframe', type=str, required=True, help='timeframe: 1m 5m 15m 30m 1h 4h 1d 1w 1M')
    # add arg verbose
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose mode')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logging.info('exbot charting ....')

    config = load_config(args.config)
    ex = exchange.Exchange(config.exchange).get()
    ex.load_markets()
    print(ex.id())
    @app.callback(
        Output("graph", "figure"),
        Input("update", "n_intervals"),
        Input("symbol", "value"),
        Input('graph', 'clickData'),
        Input('graph', 'hoverData'),
        State("graph", "relayoutData")

    )
    def update_graph(_n, symbol, click_data, hover_data,relayout_data):
        print(f"symbol: {symbol}")
        # 获取图表实时数据
        df = get_charting(symbol, args.timeframe)
        # 限制初始显示的数据
        df_display = df.tail(chart_display_size)
        print(df_display)
        # 绘制蜡烛图
        fig_candle = draw_fig_candle(df)
        # 绘制MACD指标
        fig_macd, macd_yaxis_range = draw_fig_macd(df)
        # 组合图表
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.005, row_heights=[0.7, 0.3])
        fig.add_trace(fig_candle.data[0], row=1, col=1)
        fig.add_shape(fig_candle.layout.shapes[0], row=1, col=1)
        fig.add_annotation(fig_candle.layout.annotations[0])
        fig.add_trace(fig_macd.data[0], row=2, col=1)
        fig.add_trace(fig_macd.data[1], row=2, col=1)
        fig.add_trace(fig_macd.data[2], row=2, col=1)
        # 绘制鼠标位置垂直线
        draw_fig_with_click_data(fig, click_data, df_display, macd_yaxis_range)
        draw_fig_with_hover_data(fig, hover_data, df_display, macd_yaxis_range)

        fig.update_layout(
            height=800,
            title=symbol,
            xaxis=dict(
                rangeslider=dict(
                    visible=False
                ),
                range=[df_display['date'].iloc[0], df_display['date'].iloc[-1]+timedelta(minutes=100)],
            ),
            yaxis=dict(
                side='right',
                range=[df_display['low'].min()*0.99, df_display['high'].max()*1.01],

            ),
            yaxis2=dict(
                title='MACD',
                side='right',
                range=macd_yaxis_range['range'],
            ),
            dragmode='pan',
        )
        # 设定图表到上次的位置
        fig_relayout(fig, relayout_data)

        return fig

    app.run_server(debug=True)



    
