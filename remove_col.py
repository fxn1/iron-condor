import argparse
import pandas as pd

def main():
    parser = argparse.ArgumentParser(description='Drop column from CSV')
    parser.add_argument('--in_file', type=str, default='outputs/Stock_Put_Spread_Backtest_1.csv', help='Input file for CSV (default: datas/Stock_Put_Spread_Backtest.csv)')
    parser.add_argument('--out_file', type=str, default='outputs/Stock_Put_Spread_Backtest_2.csv', help='Output file for CSV (default: datas/Stock_Put_Spread_Backtest_1.csv)')
    parser.add_argument('--col_name', type=str, default="Volume_Entry", help='column name to drop from csv file (e.g. "Cumulative_Credit_$")')
    args = parser.parse_args()

    df = pd.read_csv(args.in_file, dtype=str)
    df = df.drop(columns=[args.col_name])
    df.to_csv(args.out_file, index=False)


if __name__ == "__main__":
    main()
