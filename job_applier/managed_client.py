"""Thin synchronous protocol client; explicit instance, no env/DB/browser discovery."""
from urllib.parse import urlsplit
import httpx
from .managed_shared import ProtocolError


class Client:
    def __init__(self, base_url, instance_id, token, transport=None):
        parsed=urlsplit(base_url)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProtocolError('loopback_url_required')
        if not token or not instance_id:raise ProtocolError('explicit_credentials_required')
        self.http=httpx.Client(base_url=base_url.rstrip('/'),headers={'Authorization':'Bearer '+token,'X-JobBot-Instance':instance_id},transport=transport,timeout=15,trust_env=False,follow_redirects=False)

    def call(self, operation, **kwargs):
        if not isinstance(operation,str) or not operation.replace('_','').isalnum():raise ProtocolError('invalid_operation')
        try:
            response=self.http.get('/v1/health') if operation=='health' else self.http.post('/v1/'+operation,json=kwargs)
            data=response.json()
        except (httpx.HTTPError,ValueError) as exc:raise ProtocolError('api_unavailable') from exc
        if response.status_code>=400:raise ProtocolError(data.get('error','request_failed'))
        return data

    def close(self):self.http.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
