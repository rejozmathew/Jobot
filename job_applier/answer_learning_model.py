"""Model-only inference entry point, launched inside the authenticated Hermes runtime."""
import contextlib
import json
import sys


def main():
    request=json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        from hermes_cli.config import load_config
        from agent.auxiliary_client import call_llm
        model_config=load_config().get('model') or {}
        response=call_llm(provider=request.get('provider'),model=request.get('model') or model_config.get('default'),
            messages=[{'role':'system','content':request['instruction']},
                      {'role':'user','content':json.dumps(request['payload'])}],
            tools=[],max_tokens=1800,timeout=120)
        content=response.choices[0].message.content
    json.dump({'content':content},sys.stdout)


if __name__=='__main__':main()
