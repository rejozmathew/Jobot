"""Application documents below an owned page; one ref API across frame boundaries.

Only DOM-owned application frames are attached. Target discovery never searches
other tabs. Browser input remains on the root target and checks every ancestor.
"""
import re
from urllib.parse import parse_qs, urlsplit

from .cdp_client import CDPPage
from .managed_identity import is_same_application_scope

WORLD = 'jobbot_application_forms'


class FrameUnavailable(ValueError):
    pass


def _requisition(url):
    p = urlsplit(url)
    q = parse_qs(p.query, keep_blank_values=True)
    values = q.get('gh_jid', [])
    if p.hostname and p.hostname.endswith('.greenhouse.io'):
        values += q.get('token', [])
        match = re.search(r'/jobs/(\d+)(?:/|$)', p.path)
        if match:values.append(match[1])
    return set(values)


def application_frame(parent_url, source, attributes):
    """The assigned page's explicit application embed is its delegation boundary."""
    try:
        parent, child = urlsplit(parent_url), urlsplit(source)
        if child.scheme not in ('http', 'https') or not child.hostname or child.username or child.password:return False
        ours, theirs = _requisition(parent_url), _requisition(source)
        if len(ours) > 1 or len(theirs) > 1 or ours and theirs and ours != theirs:return False
        label = ' '.join(attributes.get(k, '') for k in ('title', 'id', 'name', 'aria-label'))
        if re.search(r'captcha|advert|verification|recaptcha|turnstile', label, re.I):return False
        if parent.netloc == child.netloc and is_same_application_scope(parent_url, source):return True
        return bool(re.search(r'application|job[\s_-]*(?:app|board|form)|grnhse|greenhouse', label, re.I))
    except (TypeError, ValueError):
        return False


async def _remote(page, expression):
    params = {'expression': expression, 'returnByValue': False}
    if getattr(page, 'context_id', None) is not None:params['contextId'] = page.context_id
    result = await page._session.call('Runtime.evaluate', params)
    if result.get('exceptionDetails'):raise FrameUnavailable('frame_document_unavailable')
    return result.get('result', {}).get('objectId')


async def _owner_call(parent, owner, function, value=None):
    params = {'objectId': owner, 'functionDeclaration': function, 'returnByValue': True,
              'arguments': [{'value': value}]}
    try:result = await parent._session.call('Runtime.callFunctionOn', params)
    except RuntimeError as exc:raise FrameUnavailable('frame_owner_unavailable') from exc
    if result.get('exceptionDetails'):raise FrameUnavailable('frame_owner_unavailable')
    return result.get('result', {}).get('value')


class FramePage(CDPPage):
    def __init__(self, router, parent, owner, frame_id, channel, context_id, url):
        super().__init__(channel, router.root.target_id, url)
        self.router, self.parent, self.owner = router, parent, owner
        self.frame_id, self.context_id = frame_id, context_id
        self.nonce = None

    def wrap(self, ref):
        return f'frame:{self.frame_id}:{self.nonce}:{ref}' if ref else ref

    async def validate(self):
        if isinstance(self.parent, FramePage):await self.parent.validate()
        root_url = await self.router.root.evaluate('location.href')
        if not is_same_application_scope(self.router.package['job']['url'], root_url):
            raise FrameUnavailable('frame_parent_job_changed')
        state = await _owner_call(self.parent, self.owner,
            'function(){return {connected:this.isConnected,src:this.src}}')
        if not state or not state['connected'] or state['src'] != self.source:
            raise FrameUnavailable('frame_owner_changed')
        try:current = await CDPPage.evaluate(self, '[location.href,window.__jobbotFrameDocument]')
        except RuntimeError as exc:raise FrameUnavailable('frame_document_changed') from exc
        if current != [self.url, self.nonce]:raise FrameUnavailable('frame_document_changed')

    async def evaluate_function(self, expression, arg=None, timeout=30.0):
        await self.validate()
        return await super().evaluate_function(expression, arg, timeout)

    async def evaluate(self, expression, arg=None, timeout=30.0):
        await self.validate()
        return await super().evaluate(expression, arg, timeout)

    async def press_key(self, key, vk=0):
        await self.validate()
        # A focus operation in the child precedes this call.
        await self.router.root.press_key(key, vk)

    async def insert_text(self, text):
        await self.validate()
        await self.router.root.insert_text(text)

    async def _map_point(self, point, scroll):
        await self.validate()
        mapped = await _owner_call(self.parent, self.owner, r'''function(p){
          if(!this.isConnected)return {reason:'frame_owner_changed'};
          // Rotation, skew and perspective cannot be inferred from an axis-aligned box.
          for(let e=this;e;e=e.parentElement){const s=getComputedStyle(e);
            if(s.transform!=='none'||s.perspective!=='none'||(s.zoom&&Number(s.zoom)!==1))
              return {reason:'frame_transform_unsupported'};}
          const coordinate=()=>{const r=this.getBoundingClientRect();
            return {x:r.left+this.clientLeft+p.x,y:r.top+this.clientTop+p.y};};
          if(p.scroll){
            this.scrollIntoView({block:'center',inline:'center',behavior:'instant'});
            for(let e=this.parentElement;e&&e!==document.documentElement&&e!==document.body;e=e.parentElement){
              if(e.scrollHeight>e.clientHeight||e.scrollWidth>e.clientWidth){
                const q=coordinate(),r=e.getBoundingClientRect();
                e.scrollBy({left:q.x-(r.left+e.clientWidth/2),top:q.y-(r.top+e.clientHeight/2),behavior:'instant'});}}
            const q=coordinate();window.scrollBy({left:q.x-innerWidth/2,top:q.y-innerHeight/2,behavior:'instant'});
          }
          const q=coordinate(),hit=document.elementFromPoint(q.x,q.y);
          return hit===this?{pointer_ready:true,...q}:{reason:'frame_control_obscured'};
        }''', dict(point, scroll=scroll))
        if not mapped or not mapped.get('pointer_ready'):return mapped or {'reason': 'frame_owner_unavailable'}
        if isinstance(self.parent, FramePage):return await self.parent._map_point(mapped, scroll)
        return mapped

    async def click_observed(self, validator, args):
        try:
            point = await self.evaluate_function(validator, dict(args, prepare_pointer=True))
            if not point.get('pointer_ready'):return dict(point, clicked=False, execution='not_executed')
            mapped = await self._map_point(point, True)
            if not mapped.get('pointer_ready'):return dict(mapped, clicked=False, execution='not_executed')
            # OOPIF input routing follows compositor updates after parent scroll.
            # Wait for a bounded paint before rechecking the mapped target.
            await self.router.root.evaluate('''()=>new Promise(resolve=>{
                const timer=setTimeout(resolve,120);requestAnimationFrame(()=>requestAnimationFrame(()=>{
                    clearTimeout(timer);resolve();}));})''')
            root = self.router.root._session
            await root.call('Input.dispatchMouseEvent', dict(type='mouseMoved', x=mapped['x'], y=mapped['y']))
            fresh = await self.evaluate_function(validator, dict(args, prepare_pointer=True, recheck_pointer=True))
            checked = await self._map_point(fresh, False) if fresh.get('pointer_ready') else {}
            if not checked.get('pointer_ready') or any(checked[k] != mapped[k] for k in ('x', 'y')):
                return {'clicked': False, 'execution': 'not_executed', 'reason': checked.get('reason', 'frame_control_changed_before_press')}
        except Exception:
            return {'clicked': False, 'execution': 'not_executed', 'reason': 'frame_reference_stale'}
        params = dict(x=mapped['x'], y=mapped['y'], button='left', clickCount=1)
        try:
            await root.call('Input.dispatchMouseEvent', dict(params, type='mousePressed', buttons=1))
            await root.call('Input.dispatchMouseEvent', dict(params, type='mouseReleased', buttons=0))
        except Exception:
            return {'clicked': False, 'execution': 'possibly_executed', 'reason': 'pointer_dispatch_unconfirmed'}
        return {'clicked': True, 'execution': 'clicked', 'activation': 'browser_pointer', 'outcome_verified': False}

class FrameRouter:
    def __init__(self, root, package):
        self.root, self.package = root, package
        self.frames, self.diagnostics = {}, []
        self.channels, self.attached = {}, set()

    async def _attach(self, channel):
        key = getattr(channel, 'session_id', None)
        if key in self.attached:return
        self.attached.add(key)
        def connected(params):
            target = params.get('targetInfo', {})
            if target.get('type') == 'iframe':
                self.channels[target['targetId']] = channel.channel(params['sessionId'])
        channel.subscribe('Target.attachedToTarget', connected)
        await channel.call('Target.setAutoAttach', {'autoAttach': True, 'waitForDebuggerOnStart': False,
            'flatten': True, 'filter': [{'type': 'iframe', 'exclude': False}, {'exclude': True}]})

    async def discover(self, parent=None, depth=0):
        parent = parent or self.root
        if depth >= 4 or len(self.frames) >= 12:
            self.diagnostics.append({'reason': 'application_frame_limit'});return self
        await self._attach(parent._session)
        parent_url = await parent.evaluate('location.href')
        count = await parent.evaluate('document.querySelectorAll("iframe").length')
        for i in range(min(count, 24)):
            if len(self.frames)>=12:
                self.diagnostics.append({'reason':'application_frame_limit'});break
            try:
                owner = await _remote(parent, f'document.querySelectorAll("iframe")[{i}]')
                details = await _owner_call(parent, owner, '''function(){return {
                    src:this.src,visible:!!this.getClientRects().length,
                    attributes:Object.fromEntries([...this.attributes].map(a=>[a.name,a.value]))}}''')
                if not details or not details['visible'] or not application_frame(parent_url, details['src'], details['attributes']):continue
                assigned, embedded = _requisition(self.package['job']['url']), _requisition(details['src'])
                if assigned and embedded and assigned != embedded:continue
                node = (await parent._session.call('DOM.describeNode', {'objectId': owner, 'depth': 0}))['node']
                fid = node.get('frameId')
                if not fid:continue
                channel = self.channels.get(fid, parent._session)
                if channel is not parent._session:
                    for domain in ('Page', 'DOM', 'Runtime'):await channel.call(domain+'.enable')
                world = await channel.call('Page.createIsolatedWorld', {'frameId': fid, 'worldName': WORLD})
                frame = FramePage(self, parent, owner, fid, channel, world['executionContextId'], details['src'])
                frame.source = details['src']
                actual = await CDPPage.evaluate(frame, 'location.href')
                # A redirect must preserve this embed's application scope.
                if actual != frame.url and not is_same_application_scope(frame.url, actual):
                    self.diagnostics.append({'reason': 'application_frame_redirect_unverified'});continue
                frame.url = actual
                frame.nonce = await CDPPage.evaluate(frame,
                    'window.__jobbotFrameDocument ||= crypto.randomUUID()')
                self.frames[fid] = frame
                await self.discover(frame, depth + 1)
            except Exception:
                self.diagnostics.append({'reason': 'application_frame_unavailable'})
        return self

    async def resolve(self, ref):
        parts = ref.split(':', 3)
        if len(parts) != 4:raise FrameUnavailable('frame_reference_invalid')
        _, fid, nonce, raw = parts
        if fid not in self.frames:await self.discover()
        frame = self.frames.get(fid)
        if not frame or frame.nonce != nonce:raise FrameUnavailable('frame_reference_stale')
        await frame.validate()
        return frame, raw


async def router_for(page, package=None):
    if package is not None:page.application_package = package
    router = getattr(page, 'application_frames', None)
    if router is None:
        package = getattr(page, 'application_package', None)
        if package is None:raise FrameUnavailable('application_frame_context_required')
        router = page.application_frames = FrameRouter(page, package)
    return router


async def resolve_control(page, target):
    if not str(target.get('ref', '')).startswith('frame:'):return page, target
    frame, raw = await (await router_for(page)).resolve(target['ref'])
    return frame, {'ref': raw}
