import faulthandler
faulthandler.enable()

from datetime import datetime, timedelta
from easy_backtest.dataset import Dataset
from easy_backtest.strategy import Strategy
from easy_backtest.recorder import Recorder
from easy_backtest.engine import BacktestEngine
from pathlib import Path
import pandas as pd
from datetime import datetime

class MyDataset(Dataset):
    def __init__(self, path:str='./backtest_1h.parquet'):
        super().__init__()
        self.path = Path(path)

    def __iter__(self):
        df = pd.read_parquet(self.path)
        df = df.drop_duplicates(subset=['symbol', 'open_time'], keep='last')
        # df['open_time'] = pd.to_datetime(df['open_time'])
        df['buy_fill'] = df.groupby("symbol")['low'].shift(-1) < df['close']
        df['sell_fill'] = df.groupby("symbol")['high'].shift(-1) > df['close']
        # df = df.dropna().reset_index(drop=True)
        for dt, group in df.groupby("open_time"):
            yield dt, group

class OKXDataset(Dataset):
    def __init__(self, path:str='./okx_backtest_1h.parquet'):
        super().__init__()
        self.path = Path(path)

    def __iter__(self):
        df = pd.read_parquet(self.path)
        df.rename(columns={
            'instrument_name':'symbol',
        }, inplace=True)
        df['vol_reverse'] = df.groupby('symbol')['momentum'].transform(lambda g: (1 / g.fillna(0).rolling(30*24).std()).clip(0, 200))
        df = df.drop_duplicates(subset=['symbol', 'open_time'], keep='last')
        # df['open_time'] = pd.to_datetime(df['open_time'])
        df['buy_fill'] = df.groupby("symbol")['low'].shift(-1) < df['close']
        df['sell_fill'] = df.groupby("symbol")['high'].shift(-1) > df['close']
        # df = df.dropna().reset_index(drop=True)
        for dt, group in df.groupby("open_time"):
            yield dt, group

class FactorNeutral(Strategy):
    def __init__(
        self,
        factor:str, # 因子名称
        ascending:bool=True, # 因子排序方式, 把看涨的排前面
        # tolerance:float=0.25,
        long_tolerance:float=0.5, # 多头容忍度
        short_tolerance:float=0.5, # 空头容忍度
        min_duration:timedelta = timedelta(hours=0),
        long_num:int = 20, # 多头持仓标的数量
        short_num:int = 20, # 空头持仓标的数量
        amount:int = 10**4, # 每个标的初始开仓金额
        vol24h_open:float = 24*25*10**4, # 24小时成交量开仓门槛是3000w u, 否则不允许开仓
        vol24h_hold:float = 24*5*10**4,  # 24小时成交量持仓门槛是1000w u, 低于强行平仓
        rebalance_interval=timedelta(hours=1)
    ):
        super().__init__()
        self.factor = factor
        self.ascending = ascending
        self.min_duration = min_duration
        self.long_tolerance = long_tolerance
        self.short_tolerance = short_tolerance
        self.long_num = long_num
        self.short_num = short_num
        self.amount = amount
        self.vol24h_open = vol24h_open
        self.vol24h_hold = vol24h_hold
        self.rebalance_interval = rebalance_interval
        # 保存标的价格数据
        self.price_dict = {}
        # 保存开仓时间, 必须持有1小时才调出
        self.open_dt_dict = {}
        # 保存上次rebalance时间
        self.last_rebalance_dt = None

    def on_data(self, dt: datetime, data: pd.DataFrame):
        # if dt >= pd.to_datetime('2023-12-01 00:00:00', utc=True):
        #     pass
        # 更新价格数据
        self.price_dict.update(dict(zip(data['symbol'], data['close'])))
        # 按因子排序
        data = data.set_index('symbol').sort_values(by=self.factor, ascending=self.ascending)
        data['rank'] = data[self.factor].rank(pct=True)

        # 多空持仓分别处理
        current_positions = self.get_position()
        assert len(current_positions) <= self.long_num + self.short_num
        long_position = {k:v for k,v in current_positions.items() if v>0}
        short_position = {k:v for k,v in current_positions.items() if v<0}

        # 计算拟调出仓位
        # 1. 因子数据缺失了的必须调出
        # 2. 超过持仓数量的
        # 3. 因子排名超出容忍度的
        # 基础需要调出的是那些缺失因子数据的
        long_out = set([symbol for symbol in long_position.keys() if symbol not in data.index or data.at[symbol, 'vol_24h'] < self.vol24h_hold])
        # long_out = set([symbol for symbol in long_position.keys() if symbol not in data.index])
        # 然后计算余下持仓的因子分位数，并排序
        long_left_holding = sorted(
            [
            (symbol, data.at[symbol, 'rank'])
            for symbol in long_position.keys()
            if symbol not in long_out
            ],
            key=lambda x:x[1],
            reverse=True
        )
        for symbol, rank in long_left_holding:
            # 持仓时间未到禁止调出
            if (dt - self.open_dt_dict[symbol]) < self.min_duration:
                continue
            # 排名超过容忍直接调出
            if rank > self.long_tolerance:
                long_out.add(symbol)
            else:
                break
        # 计算多头需要调入的标的
        # 先假设都无法成功调出（因为不确定某个标的是否会被撮合）
        long_in_n = self.long_num - len(set(long_position.keys()))
        long_in_n = 0 if long_in_n < 0 else long_in_n
        long_in = set()
        if long_in_n > 0:
            long_in = set(
                [
                symbol for symbol in data.index if (
                    symbol not in current_positions and # 空头持有难道就不能多头调入？因为平仓是按持仓计算，所以这里没问题
                    data.at[symbol, 'vol_24h'] >= self.vol24h_open
                )
                ][:long_in_n]
            )

        # 接下来处理空头
        # 基础需要调出的是那些缺失因子数据的
        short_out = set([symbol for symbol in short_position.keys() if symbol not in data.index or data.at[symbol, 'vol_24h'] < self.vol24h_hold])
        # short_out = set([symbol for symbol in short_position.keys() if symbol not in data.index])
        # 然后计算余下持仓的因子分位数，并排序
        short_left_holding = sorted(
            [
            (symbol, data.at[symbol, 'rank'])
            for symbol in short_position.keys()
            if symbol not in short_out
            ],
            key=lambda x:x[1],
            reverse=False
        )
        for symbol, rank in short_left_holding:
            # 持仓时间未到禁止调出
            if (dt - self.open_dt_dict[symbol]) < self.min_duration:
                continue
            # 排名超过容忍直接调出
            if rank < self.short_tolerance:
                short_out.add(symbol)
            else:
                break
        # 计算空头需要调入的标的
        # 先假设都能成功调出（因为不确定某个标的是否会被撮合）
        # 空头端只是为了做风控，而不是为了盈利，因为可以无风险套利注定了收益不高。溢价最高的那些一定是因为某些原因无法套利的，这种空进去风险反而过高，剔除
        # 参数是稳定的，0.7,0.8,0.9试过了，效果差不多，取0.8就行
        short_in_n = self.short_num - len(set(short_position.keys()))
        short_in_n = 0 if short_in_n < 0 else short_in_n
        short_in = set()
        if short_in_n > 0:
            short_in = set(
                [
                    symbol for symbol in data.index 
                    if (
                        symbol not in current_positions and
                        data.at[symbol, 'vol_24h'] >= self.vol24h_open
                    )
                ][-short_in_n:]
            )

        # 平仓
        for symbol in long_out | short_out:
            # 数据不存在禁止撮合
            buy_fill = data.at[symbol, 'buy_fill'] if symbol in data.index else False
            sell_fill = data.at[symbol, 'sell_fill'] if symbol in data.index else False
            qty = -current_positions[symbol]
            if (qty<0 and sell_fill) or (qty>0 and buy_fill):
                self.execute(symbol, qty)
                del self.open_dt_dict[symbol]

        # 开仓
        # 先计算总波动率，记得clip，然后开仓的时候算波动率占比
        target_set = current_positions.keys() | long_in | short_in - long_out - short_out
        total_vr = 0
        for symbol in target_set:
            vr = data.at[symbol, 'vol_reverse'] if symbol in data.index else 100
            if vr > 160:
                vr = 160
            elif vr < 60:
                vr = 60
            total_vr += vr
        total_vr += (self.long_num + self.short_num - len(target_set)) * 93

        for symbol in long_in:
            buy_fill = data.at[symbol, 'buy_fill']
            vr = data.at[symbol, 'vol_reverse']
            if vr > 160:
                vr = 160
            elif vr < 60:
                vr = 60
            wt = vr / total_vr
            if wt > 1.25 / (self.long_num + self.short_num):
                wt = 1.25 / (self.long_num + self.short_num)
            elif wt < 0.75 / (self.long_num + self.short_num):
                wt = 0.75 / (self.long_num + self.short_num)
            wt = 1 / (self.long_num + self.short_num)
            qty = self.amount * (self.long_num + self.short_num) * wt / self.price_dict[symbol]
            if buy_fill:
                self.execute(symbol, qty)
                self.open_dt_dict[symbol] = dt
        for symbol in short_in:
            sell_fill = data.at[symbol, 'sell_fill']
            vr = data.at[symbol, 'vol_reverse']
            if vr > 160:
                vr = 160
            elif vr < 60:
                vr = 60
            wt = vr / total_vr
            if wt > 1.25 / (self.long_num + self.short_num):
                wt = 1.25 / (self.long_num + self.short_num)
            elif wt < 0.75 / (self.long_num + self.short_num):
                wt = 0.75 / (self.long_num + self.short_num)
            wt = 1 / (self.long_num + self.short_num)
            qty = -self.amount * (self.long_num + self.short_num) * wt / self.price_dict[symbol]
            if sell_fill:
                self.execute(symbol, qty)
                self.open_dt_dict[symbol] = dt

class FactorNeutralNew(Strategy):
    """
    直接基于目标持仓计算的中性策略，自动实现rebalance
    """
    def __init__(
        self,
        factor:str, # 因子名称
        ascending:bool=True, # 因子排序方式, 把看涨的排前面
        # tolerance:float=0.25,
        long_tolerance:float=0.5, # 多头容忍度
        short_tolerance:float=0.5, # 空头容忍度
        min_duration:timedelta = timedelta(hours=0),
        long_num:int = 20, # 多头持仓的数量
        short_num:int = 20, # 空头持仓的数量
        amount:int = 10**4, # 每个标的初始开仓金额
        vol24h_open:float = 24*25*10**4, # 24小时成交量开仓门槛是3000w u, 否则不允许开仓
        vol24h_hold:float = 24*5*10**4,  # 24小时成交量持仓门槛是1000w u, 低于强行平仓
        rebalance_interval=timedelta(hours=1)
    ):
        super().__init__()
        self.factor = factor
        self.ascending = ascending
        self.min_duration = min_duration
        self.long_tolerance = long_tolerance
        self.short_tolerance = short_tolerance
        self.long_num = long_num
        self.short_num = short_num
        self.amount = amount
        self.vol24h_open = vol24h_open
        self.vol24h_hold = vol24h_hold
        self.rebalance_interval = rebalance_interval
        # 保存标的价格数据
        self.price_dict = {}
        # 保存开仓时间, 必须持有1小时才调出
        self.open_dt_dict = {}
        # 保存上次rebalance时间
        self.last_rebalance_dt = None

    def on_data(self, dt: datetime, data: pd.DataFrame):
        # 更新价格数据
        self.price_dict.update(dict(zip(data['symbol'], data['close'])))
        # 按因子排序
        data = data.set_index('symbol').sort_values(by=self.factor, ascending=self.ascending)
        data['rank'] = data[self.factor].rank(pct=True)
        # 分别计算多空需要保留的持仓
        position = self.get_position()
        long_target = set()
        short_target = set()
        # 计算需要保留的标的
        for symbol, quantity in position.items():
            if symbol not in data.index:
                continue
            rank = data.at[symbol, 'rank']
            if quantity > 0:
                if rank <= self.long_tolerance:
                    long_target.add(symbol)
            elif quantity < 0:
                if rank >= self.short_tolerance:
                    short_target.add(symbol)
        # 计算需要调入的标的
        for symbol in data.index:
            if self.long_num > len(long_target):
                if symbol not in position and data.at[symbol, 'vol_24h'] >= self.vol24h_open:
                    long_target.add(symbol)
        for symbol in reversed(data.index):
            if self.short_num > len(short_target):
                if symbol not in position and data.at[symbol, 'vol_24h'] >= self.vol24h_open:
                    short_target.add(symbol)
        # 计算目标持仓
        long_positions = {
            symbol: self.amount / self.price_dict[symbol]
            for symbol in long_target
        }
        short_positions = {
            symbol: -self.amount / self.price_dict[symbol]
            for symbol in short_target
        }
        target_positions = {**long_positions, **short_positions}
        # 下单
        for symbol in target_positions.keys() | position.keys():
            # 已经退市的强行平仓
            if symbol not in data.index:
                self.execute(symbol, -position.get(symbol, 0))
                continue
            target_qty = target_positions.get(symbol, 0)
            current_qty = position.get(symbol, 0)
            diff_qty = target_qty - current_qty
            if diff_qty > 0 and data.at[symbol, 'buy_fill']:
                self.execute(symbol, diff_qty)
            elif diff_qty < 0 and data.at[symbol, 'sell_fill']:
                self.execute(symbol, diff_qty)




class FactorGroup(Strategy):
    def __init__(
        self,
        factor:str, # 因子名称
        ascending:bool=True, # 因子排序方式, 把看涨的排前面
        long_num:int = 20, # 多头持仓的数量
        short_num:int = 20, # 空头持仓的数量
        amount:int=10**4, # 每个标的初始目标持仓金额
    ):
        super().__init__()
        self.factor = factor
        self.ascending = ascending
        self.long_num = long_num
        self.short_num = short_num
        self.amount = amount
        # 保存标的价格数据
        self.price_dict = {}
        # 保存开仓时间, 必须持有1小时才调出
        self.open_dt_dict = {}
        # 保存上次rebalance时间
        self.last_rebalance_dt = None

    def on_data(self, dt: datetime, data: pd.DataFrame):
        # 更新价格
        self.price_dict.update(dict(zip(data['symbol'], data['close'])))
        # 设置索引和排序
        data = data.set_index('symbol').sort_values(by=self.factor, ascending=self.ascending)
        data['rank'] = data[self.factor].rank(pct=True)
        # 计算多头目标持仓
        long_target = {}
        if self.long_num > 0:
            long_target = {
                symbol: self.amount / self.price_dict[symbol]
                for symbol in data.index[:self.long_num]
            }
        # 计算空头目标持仓
        short_target = {}
        if self.short_num > 0:
            short_target = {
                symbol: -self.amount / self.price_dict[symbol]
                for symbol in data.index[-self.short_num:]
            }
        target_positions = {**long_target, **short_target}
        current_positions = self.get_position()
        # 下单
        for symbol in target_positions.keys() | current_positions.keys():
            target_qty = target_positions.get(symbol, 0)
            current_qty = current_positions.get(symbol, 0)
            diff_qty = target_qty - current_qty
            if diff_qty != 0:
                self.execute(symbol, diff_qty)

def main():
    ds = MyDataset()
    # ds = OKXDataset()
    # 1. 一般long_tolerance > short_tolerance，均值是无交易成本下的盈亏平衡组别
    # 2. 差额表示对噪声（交易成本）-负期望（亏损组别）的权衡
    # 3. buyratio盈亏平衡组别大概在0.5分位数
    # 4. 高频的额外补偿0.15容忍度吧
    factor_name = 'premium'
    strategy = FactorNeutral(
        factor=factor_name,
        ascending=True,
        long_tolerance=0.8,
        short_tolerance=0.2,
        min_duration=timedelta(minutes=0),
        long_num=20,
        short_num=20,
        amount=10**4,
        vol24h_open=24*25*10**4,
        vol24h_hold=24*5*10**4,
        # rebalance_interval=timedelta(hours=1)
    )
    # tolerance * 100当做文件名，不要小数
    # strategy = FactorGroup(
    #     factor=factor_name,
    #     ascending=True,
    #     long_num=20,
    #     short_num=20,
    #     amount=10**4,
    # )
    recorder = Recorder(f'{factor_name}.csv')
    engine = BacktestEngine(ds, strategy, recorder, False)
    engine.run()

if __name__ == "__main__":
    main()