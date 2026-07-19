"""Update Qlib data using pytdx.

This script fetches historical data from TDX servers and appends it to
Qlib's binary data files, extending the data range beyond 2020-09-25.
"""

import struct
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def get_qlib_data_path():
    """Get Qlib data directory path."""
    return Path.home() / '.qlib' / 'qlib_data' / 'cn_data'


def read_calendar(qlib_path):
    """Read Qlib calendar file."""
    cal_file = qlib_path / 'calendars' / 'day.txt'
    with open(cal_file, 'r') as f:
        return [line.strip() for line in f.readlines()]


def read_instruments(qlib_path):
    """Read Qlib instruments file."""
    inst_file = qlib_path / 'instruments' / 'all.txt'
    instruments = []
    with open(inst_file, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) >= 1:
                instruments.append(parts[0])
    return instruments


def read_feature(qlib_path, symbol, feature):
    """Read a Qlib feature binary file."""
    feat_file = qlib_path / 'features' / symbol / f'{feature}.day.bin'
    if not feat_file.exists():
        return []
    with open(feat_file, 'rb') as f:
        data = f.read()
    n_values = len(data) // 4
    return list(struct.unpack(f'{n_values}f', data))


def write_feature(qlib_path, symbol, feature, values):
    """Write a Qlib feature binary file."""
    feat_file = qlib_path / 'features' / symbol / f'{feature}.day.bin'
    feat_file.parent.mkdir(parents=True, exist_ok=True)
    with open(feat_file, 'wb') as f:
        f.write(struct.pack(f'{len(values)}f', *values))


def symbol_to_tdx(symbol):
    """Convert Qlib symbol (SH600519) to pytdx format (market, code)."""
    if symbol.startswith('SH'):
        return 1, symbol[2:]
    elif symbol.startswith('SZ'):
        return 0, symbol[2:]
    return None, None


def fetch_stock_data(market, code, start_date):
    """Fetch historical data from pytdx."""
    from pytdx.hq import TdxHq_API

    api = TdxHq_API()

    # Try multiple servers
    servers = [
        ('218.75.126.9', 7709),
        ('115.238.56.198', 7709),
        ('124.160.88.183', 7709),
    ]

    for host, port in servers:
        try:
            api.connect(host, port)
            # Get daily bars (category 9 = daily)
            df = api.to_df(api.get_security_bars(9, market, code, 0, 800))
            api.disconnect()

            if df is None or df.empty:
                continue

            # Convert datetime to date string
            df['date'] = pd.to_datetime(df['datetime']).dt.strftime('%Y-%m-%d')

            # Filter data after start_date
            df = df[df['date'] > start_date]

            if not df.empty:
                return df
        except Exception as e:
            continue

    return None


def update_calendar(qlib_path, new_dates):
    """Update calendar file with new dates."""
    cal_file = qlib_path / 'calendars' / 'day.txt'
    with open(cal_file, 'r') as f:
        existing = set(line.strip() for line in f.readlines())

    with open(cal_file, 'a') as f:
        for date in sorted(new_dates):
            if date not in existing:
                f.write(f'{date}\n')

    return sorted(existing | set(new_dates))


def update_instruments(qlib_path, symbol, last_date):
    """Update instruments file with new date range."""
    inst_file = qlib_path / 'instruments' / 'all.txt'

    lines = []
    updated = False
    with open(inst_file, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if parts[0] == symbol:
                lines.append(f'{symbol}\t{parts[1]}\t{last_date}\n')
                updated = True
            else:
                lines.append(line)

    if not updated:
        lines.append(f'{symbol}\t{datetime.now().strftime("%Y-%m-%d")}\t{last_date}\n')

    with open(inst_file, 'w') as f:
        f.writelines(lines)


def update_symbol(qlib_path, symbol, calendar):
    """Update data for a single symbol."""
    market, code = symbol_to_tdx(symbol)
    if market is None:
        return False

    # Get last date from calendar
    last_date = calendar[-1]

    # Fetch new data from pytdx
    df = fetch_stock_data(market, code, last_date)
    if df is None or df.empty:
        return False

    # Map pytdx data to Qlib features
    feature_map = {
        'open': 'open',
        'close': 'close',
        'high': 'high',
        'low': 'low',
        'vol': 'volume',
    }

    new_dates = df['date'].tolist()

    # Update each feature
    for tdx_feat, qlib_feat in feature_map.items():
        existing = read_feature(qlib_path, symbol, qlib_feat)
        new_values = df[tdx_feat].tolist()
        write_feature(qlib_path, symbol, qlib_feat, existing + new_values)

    # Update change (daily return)
    existing_close = read_feature(qlib_path, symbol, 'close')
    if len(existing_close) > 1:
        changes = [0.0]  # First day has no change
        for i in range(1, len(existing_close)):
            if existing_close[i-1] != 0:
                changes.append((existing_close[i] - existing_close[i-1]) / existing_close[i-1])
            else:
                changes.append(0.0)
        write_feature(qlib_path, symbol, 'change', changes)

    # Update factor (assume 1.0 for now)
    existing_factor = read_feature(qlib_path, symbol, 'factor')
    factor_len = len(read_feature(qlib_path, symbol, 'close'))
    if len(existing_factor) < factor_len:
        existing_factor.extend([1.0] * (factor_len - len(existing_factor)))
    write_feature(qlib_path, symbol, 'factor', existing_factor)

    return new_dates


def main():
    """Main entry point."""
    print('=== Qlib 数据更新工具 (pytdx) ===\n')

    qlib_path = get_qlib_data_path()
    if not qlib_path.exists():
        print(f'错误: Qlib 数据目录不存在: {qlib_path}')
        sys.exit(1)

    # Read current calendar and instruments
    calendar = read_calendar(qlib_path)
    instruments = read_instruments(qlib_path)

    print(f'当前数据范围: {calendar[0]} ~ {calendar[-1]}')
    print(f'股票数量: {len(instruments)}\n')

    # Update first 10 stocks as a test
    test_symbols = instruments[:10]
    print(f'更新前 {len(test_symbols)} 只股票...')

    all_new_dates = set()
    updated_count = 0

    for symbol in test_symbols:
        print(f'  更新 {symbol}...', end=' ')
        new_dates = update_symbol(qlib_path, symbol, calendar)
        if new_dates:
            all_new_dates.update(new_dates)
            updated_count += 1
            print(f'OK ({len(new_dates)} 天)')
        else:
            print('SKIP (无新数据)')

    # Update calendar with new dates
    if all_new_dates:
        print(f'\n更新日历 ({len(all_new_dates)} 个新交易日)...')
        update_calendar(qlib_path, all_new_dates)

    # Update instruments with new date range
    if all_new_dates:
        last_date = max(all_new_dates)
        print(f'更新股票列表 (最后日期: {last_date})...')
        for symbol in test_symbols:
            update_instruments(qlib_path, symbol, last_date)

    print(f'\n完成! 更新了 {updated_count}/{len(test_symbols)} 只股票')

    # Verify
    calendar = read_calendar(qlib_path)
    print(f'新数据范围: {calendar[0]} ~ {calendar[-1]}')


if __name__ == '__main__':
    main()
