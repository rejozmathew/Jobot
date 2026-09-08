"""Use the installed Hermes Gmail skill with the configured mailbox credential."""
import argparse
import importlib.util
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--script',required=True)
    parser.add_argument('--token-file',required=True)
    args,remaining=parser.parse_known_args()
    spec=importlib.util.spec_from_file_location('jobbot_google_api',args.script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TOKEN_PATH=Path(args.token_file)
    sys.argv=[args.script,*remaining]
    module.main()


if __name__=='__main__':main()
