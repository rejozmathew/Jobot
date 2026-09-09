"""Use the installed Hermes Gmail skill with the configured mailbox credential."""
import argparse
import importlib.util
from pathlib import Path
import sys


def mailbox_handoff(config):
    """Expose the configured invocation, never credential content or mail bodies."""
    script=config.get('gmail_script');token=config.get('mailbox_token_path')
    available=bool(script and token and Path(script).is_file() and Path(token).is_file())
    return {'available':available,'wrapper_argv':[sys.executable,'-m','job_applier.hermes_gmail',
        '--script',script,'--token-file',token,'gmail'] if available else [],
        'instruction':'Use the existing Hermes Gmail skill to read the relevant email. The executor chooses the code closest to the request timestamp, rechecking delayed mail as needed, then supplies the code to credentials mode verification or browser fill. There is no separate mailbox-verifier approval.' if available else
        'Configured mailbox is unavailable. Inspect the actual challenge and available recovery.'}


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
