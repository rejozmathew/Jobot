/* Original synthetic fixture, NOT captured iCIMS markup and NOT production code. */
(() => {
  'use strict';
  const app = document.querySelector('#application');
  const panel = document.querySelector('.simplify-jobs-shadow-root').attachShadow({mode: 'open'});
  const counters = {profileSubmits: 0, screeningSubmits: 0, finalSubmits: 0,
    autofillClicks: 0, stopClicks: 0, formInput: 0, formChange: 0, formFocus: 0, invalid: 0};
  const record = (event, key) => document.addEventListener(event, () => counters[key]++, true);
  record('input', 'formInput'); record('change', 'formChange');
  record('focus', 'formFocus'); record('invalid', 'invalid');
  const history = [];
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const field = (id, label, options = {}) => {
    const type = options.type || 'text';
    const required = options.required ? ' required' : '';
    const star = options.required ? '*' : '';
    const input = type === 'textarea'
      ? `<textarea id="${id}" name="${id}"${required}></textarea>`
      : `<input id="${id}" name="${id}" type="${type}"${required}${options.autocomplete ? ` autocomplete="${options.autocomplete}"` : ''}>`;
    return `<div class="field"><label for="${id}">${escape(label)}${star}</label>${input}</div>`;
  };
  const step = (name, n) => {
    app.innerHTML = `<h1>Director Data Engineering Artificial Intelligence — TEST-19423</h1>
      <nav aria-label="Application progress">Step <span aria-current="step">${n}: ${escape(name)}</span> of 4</nav>`;
    history.push(name);
    window.fixture.phase = name;
  };
  const liveFill = (id, value) => {
    // Deliberately assign the property only; no initial HTML value attribute.
    document.getElementById(id).value = value;
  };
  const reviewRows = ['Resume', 'Preferred Name', 'Text Consent', 'Type', 'Please specify further',
    'Reason for Leaving', 'Reason for Leaving', '6 of 9 Experience', '7 of 9 Experience',
    '8 of 9 Experience', '9 of 9 Experience', 'Reason for Leaving', 'Reason for Leaving',
    'Reason for Leaving', 'Reason for Leaving'];

  function setSimplify(state = 'needs_review') {
    const active = state === 'active';
    const status = active ? 'Autofilling. Filling your application.' :
      state === 'unknown' ? 'Application assistant' :
      state === 'complete' ? 'Autofill complete! 0 fields need review.' :
      'Autofill complete! 15 fields need review.';
    panel.innerHTML = `<style>:host {font-family:system-ui} section {padding:1rem} li {margin:.45rem 0} button {padding:.5rem}</style>
      <section aria-label="Autofill results"><h2>Simplify — synthetic panel</h2>
      <div${active ? ' aria-busy="true"' : ''}>${status}</div>
      ${state === 'needs_review' ? `<h3>Need to review(15)</h3><ul>${reviewRows.map(t => `<li>${escape(t)}</li>`).join('')}</ul>` : ''}
      <button type="button">${active ? 'Stop Autofill' : 'Run Autofill Again'}</button></section>`;
    panel.querySelector('button').addEventListener('click', () => {
      if (active) { counters.stopClicks++; setSimplify('needs_review'); }
      else { counters.autofillClicks++; setSimplify('active'); if(Number.isFinite(window.fixture.autofillDelay))setTimeout(()=>setSimplify('needs_review'),window.fixture.autofillDelay); }
    });
    window.fixture.simplifyState = state;
  }

  function profile() {
    step('Candidate Profile', 1);
    let html = `<h2>Candidate Profile</h2>
      <div role="alert" id="server-error">Error: Invalid Data Error. Please check all information before trying again.<ul><li><a href="#password">Password: required.</a></li></ul></div>
      <form id="profile-form">
      <section class="upload-widget" aria-labelledby="resume-title">
        <h3 id="resume-title">Resume</h3><label for="resume">Please upload your resume*</label>
        <input type="file" id="resume" name="resume" accept=".pdf">
        <p class="uploaded-document"><a href="#synthetic-upload">synthetic_resume.pdf</a></p>
        <button type="button" id="replace-resume">Replace Resume</button>
      </section>
      <fieldset><legend>Create a login</legend>
        ${field('login','Login',{required:true,type:'email'})}
        ${field('password','Password',{required:true,type:'password',autocomplete:'new-password'})}
        ${field('confirmation','Password (Re-enter)',{required:true,type:'password',autocomplete:'new-password'})}
      </fieldset>
      <fieldset><legend>Enter your information</legend>
        ${field('first-name','First Name',{required:true})}
        ${field('last-name','Last Name',{required:true})}
        ${field('email','Email',{required:true,type:'email'})}
        <div class="field"><label for="state">State*</label><select id="state" name="state" required><option value="">Please select</option><option value="IL">Illinois</option></select></div>
        ${field('preferred-name','Preferred Name')}
        <div class="field"><label for="text-consent">Text Consent: Do you consent to receive text messages?</label><select id="text-consent" name="text-consent"><option value="">Please select</option><option value="yes">Yes</option><option value="no">No</option></select></div>
        ${field('type','Type')}${field('specify','Please specify further')}
      </fieldset>`;
    for (let i = 1; i <= 9; i++) html += `<fieldset id="experience-${i}"><legend>Professional / Volunteer Experience (${i})</legend>
      ${field('employer-'+i, 'Employer', {required:true})}${field('title-'+i,'Title',{required:true})}
      ${field('leaving-'+i,'Reason for Leaving',{type:'textarea'})}</fieldset>`;
    html += `<button type="submit" id="submit-profile">Submit Profile</button></form>`;
    app.insertAdjacentHTML('beforeend', html);
    liveFill('login','candidate@example.invalid'); liveFill('first-name','Synthetic');
    liveFill('last-name','Candidate'); liveFill('email','candidate@example.invalid'); liveFill('state','IL');
    for (let i=1; i<=9; i++) { liveFill('employer-'+i,'Synthetic Employer '+i); liveFill('title-'+i,'Synthetic Role '+i); }
    document.querySelector('#profile-form').addEventListener('submit', event => {
      event.preventDefault();
      if (document.querySelector('#password').value !== document.querySelector('#confirmation').value) {
        document.querySelector('#server-error').textContent = 'Password confirmation does not match.';
        return;
      }
      counters.profileSubmits++; screening();
    });
    setSimplify('needs_review');
  }

  function screening() {
    step('Screening Questions', 2);
    const questions = [
      ['authorized','Are you legally authorized to work in the country for this role?'],
      ['sponsorship','Will you now or in the future require sponsorship?'],
      ['prior','Have you previously worked for this employer or its predecessor?'],
      ['relatives','Do you have relatives employed by this employer?']
    ];
    app.insertAdjacentHTML('beforeend', `<h2>Screening Questions</h2><form id="screening-form">${questions.map(([id,q]) =>
      `<fieldset><legend>${escape(q)}*</legend><label><input type="radio" name="${id}" value="yes" required> Yes</label>
      <label><input type="radio" name="${id}" value="no" required> No</label></fieldset>`).join('')}
      <button type="submit" id="screening-next">Continue</button></form>`);
    document.querySelector('[name=authorized][value=yes]').checked = true;
    document.querySelector('[name=sponsorship][value=yes]').checked = true;
    document.querySelector('#screening-form').addEventListener('submit', event => {
      event.preventDefault(); counters.screeningSubmits++; review();
    });
    setSimplify('unknown');
  }

  function review() {
    step('Review Application', 3);
    app.insertAdjacentHTML('beforeend', `<h2>Review Application</h2><p>This is a local synthetic review. No real employer receives it.</p>
      <form id="review-form"><button type="submit" id="final-submit">Submit Application</button></form>`);
    document.querySelector('#review-form').addEventListener('submit', event => {
      event.preventDefault(); counters.finalSubmits++;
      step('Application Received', 4);
      app.insertAdjacentHTML('beforeend','<h2>Application received</h2><p>Thank you. Your synthetic application for TEST-19423 has been received.</p>');
      setSimplify('complete');
    });
    setSimplify('complete');
  }

  function addVariant(name) {
    if (name === 'optional-invalid') {
      document.querySelector('#profile-form').insertAdjacentHTML('beforeend',field('optional-email','Optional alternate email',{type:'email'}));
      liveFill('optional-email','not-an-email');
    } else if (name === 'checkboxes') {
      document.querySelector('#profile-form').insertAdjacentHTML('beforeend',`<fieldset><legend>Independent required acknowledgements</legend>
        <label><input type="checkbox" name="ack" id="ack-a" required checked> Acknowledgement A*</label>
        <label><input type="checkbox" name="ack" id="ack-b" required> Acknowledgement B*</label></fieldset>`);
    } else if (name === 'two-forms') {
      app.insertAdjacentHTML('beforeend',`<form id="decoy-form"><fieldset><legend>First form question*</legend>
        <label><input type="radio" name="shared-name" required checked value="yes">Yes</label></fieldset></form>
        <form id="other-form"><fieldset><legend>Second form question*</legend>
        <label><input type="radio" name="shared-name" required value="yes">Yes</label>
        <label><input type="radio" name="shared-name" required value="no">No</label></fieldset></form>`);
    } else if (name === 'shadow') {
      const host=document.createElement('section'); host.id='employer-widget'; app.append(host);
      host.attachShadow({mode:'open'}).innerHTML=`<h3>Employer open-root widget</h3><label for="shadow-field">Required shadow field*</label><input id="shadow-field" required>
        <label for="shadow-password">Private shadow password</label><input id="shadow-password" type="password">`;
    } else if (name === 'closed-shadow') {
      const host=document.createElement('section'); host.id='opaque-employer-widget';
      host.setAttribute('role','group'); host.setAttribute('aria-label','Opaque employer widget'); app.append(host);
      host.attachShadow({mode:'closed'}).innerHTML='<label>Hidden implementation<input required></label>';
      // An ordinary DOM reader cannot prove what is inside; do not infer it from this fixture API.
    } else if (name === 'hidden-required') {
      document.querySelector('#profile-form').insertAdjacentHTML('beforeend','<label style="display:none">CSS-hidden but native-validating<input id="hidden-native-required" required></label>');
    } else if (name === 'upload-error') {
      document.querySelector('#server-error').textContent='Resume: required. The uploaded document could not be accepted.';
    } else if (name === 'active' || name === 'unknown') setSimplify(name);
  }

  window.fixture = {
    counters, history, phase: null, simplifyState: null, profile, screening, review, setSimplify, addVariant,
    addRequired() { document.querySelector('form').insertAdjacentHTML('beforeend',field('late-required','Newly revealed required answer',{required:true})); },
    replacePassword() { const old=document.querySelector('#password'); const fresh=old.cloneNode(); old.replaceWith(fresh); return fresh; },
    addFields(count) {
      if (!Number.isInteger(count) || count<0 || count>10000) throw new Error('invalid synthetic field count');
      const region=document.createElement('section'); region.id='large-form-fixture';
      region.innerHTML=Array.from({length:count},(_,i)=>field('bench-'+i,'Synthetic benchmark field '+i)).join(''); app.append(region);
    }
  };
  const scenario=new URL(location.href).searchParams.get('scenario') || 'profile';
  if (scenario === 'screening') screening();
  else if (scenario === 'review') review();
  else { profile(); if (scenario !== 'profile') addVariant(scenario); }
})();
