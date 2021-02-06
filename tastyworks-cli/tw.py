import argparse

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	subparsers = parser.add_subparsers()
	watchlist = subparsers.add_parser('watchlist', help='Display and sort information about symbols from one of your watchlists.')
	portfolio = subparsers.add_parser('portfolio', help='View data about your portfolio as a whole and assess portfolio risk.')
	option = subparsers.add_parser('option', help='Lookup, buy, or sell options.')
	stock = subparsers.add_parser('stock', help='Lookup, buy, or sell stocks.')
	future = subparsers.add_parser('future', help='Lookup, buy, or sell futures.')
	order = subparsers.add_parser('order', help='View, replace, and cancel recent orders.')

	parser.parse_args()
