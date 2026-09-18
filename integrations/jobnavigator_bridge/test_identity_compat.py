"""Run within the installed bridge's synthetic test suite."""
from jobnavigator_bridge.common import digest
from tests.support import Base, job


class IdentityCompatibilityTests(Base):
    def test_identity_representation_upgrade_keeps_delivery_receipts(self):
        posting = job(url='https://www.linkedin.com/jobs/view/1234567890',
                      application_type='linkedin_easy_apply', resolution_status='not_required')
        original = self.bot.identities
        self.bot.identities = lambda urls, budget: [
            {'canonical': row['canonical'], 'identity': digest([row['canonical']])}
            for row in original(urls, budget)]
        _, state = self.run_jobs([posting])
        before = dict(state.rows()[0])
        receipts = list(state.db.execute('SELECT * FROM receipts'))
        self.bot.identities = lambda urls, budget: [
            {'canonical': row['canonical'], 'identity': digest(['linkedin', '1234567890'])}
            for row in original(urls, budget)]
        result, _ = self.run_jobs([posting], state=state)
        self.assertEqual('receipt_retained', result['records'][0]['reason'])
        self.assertEqual(before['target_key'], state.rows()[0]['target_key'])
        self.assertEqual(receipts, list(state.db.execute('SELECT * FROM receipts')))
        self.assertEqual(1, len(self.bot.intakes))

    def test_changed_source_id_still_requires_existing_review(self):
        posting = job(external_id='old')
        _, state = self.run_jobs([posting])
        result, _ = self.run_jobs([dict(posting, external_id='different')], state=state)
        self.assertEqual('source_identity_changed', result['records'][0]['reason'])
        self.assertEqual(1, len(self.bot.intakes))
