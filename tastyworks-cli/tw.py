import argparse

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	subparsers = parser.add_subparsers()
	chain = subparsers.add_parser('chain')
	chain.add_argument('--month', '-m', type=int, default=1, help='List the options chain for the given month.')

	parser.parse_args()
