"""Optional Greenhouse email workaround; remove its private config to disable it.

This module never connects to mail, changes credentials or updates candidate records.
Callers retain their normal behavior when no enabled route is configured.
"""


def email_route(config, platform):
    route=(config.get('email_routes') or {}).get(platform) if platform=='greenhouse' else None
    if not isinstance(route,dict) or route.get('enabled') is False or not route.get('application_email'):return {}
    application=route['application_email']
    mailbox=route.get('verification_mailbox') or application
    return {'platform':platform,'application_email':application,'verification_mailbox':mailbox,
            'delivery':'forwarded' if mailbox!=application else 'direct'}


def routed_profile(profile, route):
    if not route:return profile
    return dict(profile,identity=dict(profile.get('identity') or {},email=route['application_email']))


def routed_email_answer(question, route):
    if not route or question['kind']!='text':return None
    if (question['field'].casefold() in ('email','email_address','candidate_email') or
        question['question'].strip().rstrip('*').strip().casefold() in ('email','email address','e-mail','e-mail address')):
        return route['application_email']
    return None


def route_instruction(route):
    if not route:return ''
    return (f"For {route['platform']}, use {route['application_email']} on the application form after Simplify and before Submit or requesting a code, including after reload/refill. "
        f"Read verification emails in {route['verification_mailbox']} using the existing configured mailbox connection. "
        +('The application recipient and connected inbox intentionally differ: messages are forwarded; personal mailbox access is not required. '
          'Do not request personal-inbox integration or conclude verification is unavailable merely because these addresses differ. '
          'Search the connected inbox for the forwarded message, matching original recipient, employer and current request time; do not require its outer To header to equal the application address. '
          if route['delivery']=='forwarded' else '')
        +'Forwarding configuration is not proof of delivery: inspect actual mail, recheck delayed mail and follow existing recovery if absent. ')


def routed_mailbox(config, platform, handoff):
    route=email_route(config,platform)
    if route:return dict(handoff,email_route=route,instruction=handoff['instruction']+' '+route_instruction(route))
    if platform in (None,'unknown','linkedin'):
        pending=email_route(config,'greenhouse')
        if pending:return dict(handoff,email_routes={'greenhouse':pending},
            instruction=handoff['instruction']+' If the owned application is recognized as Greenhouse: '+route_instruction(pending))
    return handoff
