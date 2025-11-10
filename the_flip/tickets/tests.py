from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Game, Maintainer, ProblemReport


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class ReportCreateViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.game = Game.objects.create(
            name='Test Game',
            manufacturer='Bally',
            year=1995,
            type=Game.TYPE_SS,
            status=Game.STATUS_GOOD,
        )
        self.url = reverse('report_create')

    def _submission_payload(self, **overrides):
        payload = {
            'game': self.game.pk,
            'problem_type': ProblemReport.PROBLEM_STUCK_BALL,
            'problem_text': 'Ball stuck in left ramp.',
            'reported_by_name': 'Visitor',
            'reported_by_contact': 'visitor@example.com',
        }
        payload.update(overrides)
        return payload

    def test_anonymous_submission_records_ip(self):
        response = self.client.post(
            self.url,
            self._submission_payload(),
            HTTP_USER_AGENT='UnitTest/1.0',
            HTTP_X_FORWARDED_FOR='203.0.113.5',
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.get()
        self.assertIsNone(report.reported_by_user)
        self.assertEqual(report.reported_by_name, 'Visitor')
        self.assertEqual(report.ip_address, '203.0.113.5')
        self.assertEqual(report.device_info, 'UnitTest/1.0')

    def test_authenticated_submission_records_user_and_contact(self):
        user = get_user_model().objects.create_user(
            username='maintainer',
            email='tech@example.com',
            password='pass1234',
            first_name='Tech',
            last_name='One',
        )
        Maintainer.objects.create(user=user, phone='555-1234')
        self.client.login(username='maintainer', password='pass1234')

        response = self.client.post(
            self.url,
            self._submission_payload(problem_text='Coil burnt out.'),
            REMOTE_ADDR='198.51.100.42',
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.get()
        self.assertEqual(report.reported_by_user, user)
        self.assertEqual(report.reported_by_name, 'Tech One')
        self.assertEqual(report.reported_by_contact, 'tech@example.com')
        self.assertEqual(report.ip_address, '198.51.100.42')

    @override_settings(REPORT_SUBMISSION_RATE_LIMIT_MAX=2, REPORT_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS=3600)
    def test_rate_limit_blocks_submissions_from_same_ip(self):
        payload = self._submission_payload(problem_text='Repeated issue.')
        headers = {'HTTP_X_FORWARDED_FOR': '203.0.113.8'}

        for _ in range(2):
            response = self.client.post(self.url, payload, **headers)
            self.assertEqual(response.status_code, 302)

        response = self.client.post(self.url, payload, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many problem reports from this device', status_code=200)
        self.assertEqual(ProblemReport.objects.count(), 2)
