"""Trusted pointer activation of styled native controls, with isolated forms."""
import asyncio

import pytest

from job_applier.browser_controls import observe, form_action
from test_embedded_forms import fixture_browser


@pytest.mark.parametrize('mode', ['top', 'same', 'cross'])
@pytest.mark.parametrize('kind', ['checkbox', 'radio'])
def test_zero_size_native_control_uses_its_associated_label(tmp_path, monkeypatch, mode, kind):
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture, 'FORM_HTML', f'''<!doctype html><html><body>
      <input id="choice" type="{kind}" required style="position:absolute;width:0;height:0;margin:0;padding:0;appearance:none">
      <label for="choice" style="display:block;width:250px;height:40px">Approved consent</label>
      <script>choice.dataset.changes='0';choice.dataset.trusted='false';
      choice.onchange=e=>{{choice.dataset.changes=String(Number(choice.dataset.changes)+1);
        choice.dataset.trusted=String(e.isTrusted)}};</script></body></html>''')
    async def run():
        async with fixture_browser(tmp_path, mode) as (page, package, _):
            screen = await observe(page, package)
            field = next(f for f in screen['inventory'] if f['label'] == 'Approved consent')
            result = await form_action(page, {'method': 'check', 'ref': field['ref'], 'value': True})
            assert result.get('committed'), result
            repeated = await form_action(page, {'method': 'check', 'ref': field['ref'], 'value': True})
            assert repeated.get('committed'), repeated
            from job_applier.browser_frames import resolve_control
            document, _ = await resolve_control(page, {'ref': field['ref']})
            assert await document.evaluate("choice.checked && choice.dataset.changes==='1' && choice.dataset.trusted==='true'")
            if kind == 'checkbox':
                await document.evaluate('choice.required=false')
                unchecked = await form_action(page, {'method': 'check', 'ref': field['ref'], 'value': False})
                assert unchecked.get('committed'), unchecked
                assert await document.evaluate("!choice.checked && choice.dataset.changes==='2'")
    asyncio.run(run())


@pytest.mark.parametrize('variant', ['overlay', 'disabled', 'unrelated_label', 'interactive_child'])
def test_label_recovery_preserves_actual_pointer_and_control_checks(tmp_path, monkeypatch, variant):
    import test_embedded_forms as fixture
    extra = '<div style="position:fixed;inset:0;background:white;z-index:20"></div>' if variant == 'overlay' else ''
    attrs = 'disabled' if variant == 'disabled' else ''
    binding = 'other' if variant == 'unrelated_label' else 'choice'
    child = '<button style="width:100%;height:100%" onclick="window.otherClicks++">Different action</button>' if variant == 'interactive_child' else 'Approved consent'
    monkeypatch.setattr(fixture, 'FORM_HTML', f'''<!doctype html><html><body>
      <input id="choice" type="checkbox" {attrs} style="position:absolute;width:0;height:0;margin:0;padding:0;appearance:none">
      <label for="{binding}" style="display:block;width:250px;height:40px">{child}</label>{extra}
      <script>window.otherClicks=0;</script></body></html>''')
    async def run():
        async with fixture_browser(tmp_path, 'top') as (page, package, _):
            await observe(page, package)
            result = await form_action(page, {'method': 'check', 'selector': '#choice', 'value': True})
            assert not result.get('committed'), result
            assert await page.evaluate('!choice.checked && otherClicks===0')
    asyncio.run(run())
