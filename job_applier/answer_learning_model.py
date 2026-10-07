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
        provider=request.get('provider') or model_config.get('provider')
        model=request.get('model') or model_config.get('default')
        # Bind the auxiliary client's main-model recovery to this task's model,
        # rather than the unrelated default in the installed Hermes profile.
        from hermes_cli.runtime_provider import resolve_runtime_provider
        runtime=resolve_runtime_provider(requested=provider,target_model=model)
        main_runtime=dict(runtime,provider=provider,model=model)
        response=call_llm(provider=provider,model=model,main_runtime=main_runtime,
            reasoning_config={'enabled':True,'effort':request['effort']} if request.get('effort') else None,
            messages=[{'role':'system','content':request['instruction']},
                      {'role':'user','content':json.dumps(request['payload'])}],
            tools=[],max_tokens=1800,timeout=120)
        content=response.choices[0].message.content
    json.dump({'content':content},sys.stdout)


if __name__=='__main__':main()
