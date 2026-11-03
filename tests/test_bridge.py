import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from lumia_bridge import State, Server


def jpeg(width=640, height=480):
    output = io.BytesIO()
    Image.new('RGB', (width, height), (20, 80, 180)).save(output, 'JPEG')
    return output.getvalue()


def capability_fixture():
    def control(name, low, high, nullable=False):
        return dict(name=name, supported=True, value_type='integer', unit='test units',
                    nullable=nullable, minimum=low, maximum=high, choices=[])
    return dict(version=1, cameras=[dict(camera='rear', autofocus_supported=True, focus_region_supported=True,
        controls=[control('iso', 100, 3200, True), control('exposure_time_us', 100, 1000000, True),
                  control('manual_focus_position', 0, 1000)]),
        dict(camera='front', autofocus_supported=False, focus_region_supported=False, controls=[])])


class HTTPWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = dict(agent_token='agent_' + 'a' * 32, device_token='phone_' + 'b' * 32)
        self.state = State(self.temp.name, self.config)
        self.server = Server(('127.0.0.1', 0), self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.session = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def call(self, path, payload=None, role='agent', raw=False, session=None, extra_headers=None):
        data = payload if isinstance(payload, bytes) else None if payload is None else json.dumps(payload).encode()
        headers = {} if role is None else {'Authorization': 'Bearer ' + self.config[role + '_token']}
        headers.update(extra_headers or {})
        if role == 'device' and (session or self.session):
            headers['X-Device-Session'] = session or self.session
        req = Request(self.base + path, data=data, headers=headers)
        try:
            with urlopen(req, timeout=20) as response:
                result = response.read()
                return response.status, result if raw else json.loads(result)
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def register(self, protocol_version=1):
        code, self.session = self.call('/device/register', {'model': 'SIMULATED Lumia 1020', 'os': '8.1', 'protocol_version': protocol_version}, role='device', raw=True)
        self.session = self.session.decode()
        self.assertEqual(code, 200)

    def acquire(self, kind='preview', **params):
        code, job = self.call('/v1/preview' if kind == 'preview' else '/v1/captures', params)
        self.assertEqual(code, 202)
        code, command = self.call('/device/next', role='device', raw=True)
        self.assertEqual(code, 200)
        self.assertEqual(command.decode().split('\n')[0], job['id'])
        return job

    def test_offline_and_role_separation(self):
        self.assertEqual(self.call('/v1/preview', {})[0], 503)
        self.assertEqual(self.call('/v1/status', role='device')[0], 401)
        self.assertEqual(self.call('/device/register', {}, role='agent')[0], 401)
        self.assertEqual(self.call('/device/next', role='device')[0], 409)

    def test_local_browser_explorer_and_spec(self):
        code, page = self.call('/docs', role=None, raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b'/static/swagger/swagger-ui-bundle.js', page)
        self.assertNotIn(b'https://', page)
        self.assertNotIn(self.config['agent_token'].encode(), page)
        code, spec = self.call('/openapi.json', role=None)
        self.assertEqual(code, 200)
        self.assertEqual(spec['servers'][0]['url'], '/')
        self.assertEqual(spec['components']['securitySchemes']['agentToken']['scheme'], 'bearer')
        self.assertIn('/v1/images/{id}/crop', spec['paths'])
        self.assertEqual(self.call('/v1/status', role=None)[0], 401)

    def test_explorer_assets_are_local_and_paths_are_fixed(self):
        code, init = self.call('/static/swagger-init.js', role=None, raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b'validatorUrl: null', init)
        self.assertIn(b'persistAuthorization: false', init)
        code, bundle = self.call('/static/swagger/swagger-ui-bundle.js', role=None, raw=True)
        self.assertEqual(code, 200)
        self.assertGreater(len(bundle), 100_000)
        self.assertEqual(self.call('/static/swagger/../../../config.json')[0], 404)

    def test_preview_round_trip_and_crop(self):
        self.register()
        job = self.acquire()
        original = jpeg()
        self.assertEqual(self.call('/device/result/' + job['id'], original, role='device')[0], 200)
        _, result = self.call('/v1/jobs/' + job['id'])
        self.assertEqual(result['status'], 'done')
        image = result['image']
        self.assertEqual(self.call(image['url'], raw=True)[1], original)
        code, crop = self.call('/v1/images/' + image['id'] + '/crop', dict(x=100, y=50, width=240, height=120))
        self.assertEqual(code, 201)
        self.assertEqual((crop['width'], crop['height']), (240, 120))
        self.assertEqual(self.call('/v1/images/' + image['id'] + '/crop', dict(x=600, y=0, width=100, height=1))[0], 400)
        _, thumb = self.call('/v1/images/' + image['id'] + '/thumbnail.jpg?max=128', raw=True)
        self.assertEqual(Image.open(io.BytesIO(thumb)).size, (128, 96))
        reloaded = State(self.temp.name, self.config)
        self.assertEqual(len(reloaded.images), 2)

    def test_full_resolution_original_is_preserved(self):
        self.register()
        job = self.acquire('capture')
        original = jpeg(7136, 5360)
        self.assertEqual(self.call('/device/result/' + job['id'], original, role='device')[0], 200)
        _, result = self.call('/v1/jobs/' + job['id'])
        self.assertEqual(result['status'], 'done')
        self.assertEqual(result['image']['width'], 7136)
        self.assertEqual(self.call(result['image']['url'], raw=True)[1], original)

    def test_rear_capture_does_not_silently_fall_back_to_5mp(self):
        self.register()
        job = self.acquire('capture')
        self.call('/device/result/' + job['id'], jpeg(), role='device')
        _, result = self.call('/v1/jobs/' + job['id'])
        self.assertEqual(result['status'], 'error')
        self.assertIn('30 MP', result['error'])

    def test_front_camera_accepts_its_actual_resolution(self):
        self.register()
        job = self.acquire('capture', camera='front')
        self.call('/device/result/' + job['id'], jpeg(1280, 960), role='device')
        self.assertEqual(self.call('/v1/jobs/' + job['id'])[1]['status'], 'done')

    def test_expired_job_rejects_late_upload(self):
        self.register()
        job = self.acquire()
        self.state.jobs[job['id']]['_deadline'] = time.monotonic() - 1
        self.assertEqual(self.call('/device/result/' + job['id'], jpeg(), role='device')[0], 410)
        self.assertEqual(len(self.state.images), 0)

    def test_session_change_cancels_old_work(self):
        self.register()
        previous = self.session
        job = self.acquire()
        self.register()
        self.assertEqual(self.call('/device/result/' + job['id'], jpeg(), role='device', session=previous)[0], 409)
        self.assertEqual(self.call('/v1/jobs/' + job['id'])[1]['status'], 'error')

    def test_queue_bound_and_input_validation(self):
        self.register()
        self.assertEqual(self.call('/v1/captures', {'camera': 'other'})[0], 400)
        self.assertEqual(self.call('/v1/captures', {'focus': 'false'})[0], 400)
        for _ in range(16):
            self.assertEqual(self.call('/v1/preview', {})[0], 202)
        self.assertEqual(self.call('/v1/preview', {})[0], 429)

    def test_invalid_jpeg_does_not_complete_job(self):
        self.register()
        job = self.acquire()
        self.assertEqual(self.call('/device/result/' + job['id'], b'not an image', role='device')[0], 400)
        self.assertEqual(self.call('/v1/jobs/' + job['id'])[1]['status'], 'running')

    def test_focus_range_requires_capable_phone_and_valid_request(self):
        self.register()
        self.assertEqual(self.call('/v1/captures', {'focus_range': 'normal'})[0], 409)
        self.assertEqual(self.call('/v1/captures', {'focus_range': 'other'})[0], 400)
        self.assertEqual(self.call('/v1/preview', {'focus_range': 'normal', 'focus': False})[0], 400)
        self.register(protocol_version=2)
        self.assertEqual(self.call('/v1/captures', {'focus_range': 'normal', 'camera': 'front'})[0], 400)
        job = self.acquire('preview', focus=True, focus_range='normal')
        self.assertTrue(job['focus'])
        self.assertEqual(job['focus_range'], 'normal')

    def test_reported_focus_result_survives_with_original_jpeg(self):
        self.register(protocol_version=2)
        job = self.acquire('preview', focus=True, focus_range='normal')
        original = jpeg()
        headers = {'X-Camera-Focus-Status': 'locked', 'X-Camera-Focus-Attempts': '2',
                   'X-Camera-Focus-Range': 'normal', 'X-Camera-Focus-Ranges': 'normal,macro,full'}
        self.assertEqual(self.call('/device/result/' + job['id'], original, role='device', extra_headers=headers)[0], 200)
        image = self.call('/v1/jobs/' + job['id'])[1]['image']
        self.assertEqual(image['focus_status'], 'locked')
        self.assertEqual(image['focus_attempts'], 2)
        self.assertEqual(image['supported_focus_ranges'], ['normal', 'macro', 'full'])
        self.assertEqual(self.call(image['url'], raw=True)[1], original)
        self.assertEqual(State(self.temp.name, self.config).images[image['id']]['focus_range'], 'normal')

    def test_focus_failure_and_invalid_metadata_do_not_claim_success(self):
        self.register(protocol_version=2)
        job = self.acquire('preview', focus=True)
        self.assertEqual(self.call('/device/result/' + job['id'], jpeg(), role='device', extra_headers={
            'X-Camera-Focus-Status': 'locked', 'X-Camera-Focus-Attempts': '0'})[0], 400)
        self.assertEqual(len(self.state.images), 0)
        self.assertEqual(self.call('/device/error/' + job['id'], b'Autofocus did not lock after two attempts.', role='device')[0], 200)
        result = self.call('/v1/jobs/' + job['id'])[1]
        self.assertEqual(result['status'], 'error')
        self.assertNotIn('image', result)

    def test_capabilities_drive_schema_validation_and_wire_controls(self):
        self.register(protocol_version=3)
        self.assertFalse(self.call('/v1/capabilities')[1]['ready'])
        self.assertEqual(self.call('/device/capabilities', capability_fixture(), role='device')[0], 200)
        self.assertTrue(self.call('/v1/capabilities')[1]['ready'])
        schema = self.call('/openapi.json', role=None)[1]['components']['schemas']['CameraRequest']['properties']['controls']
        self.assertEqual(schema['properties']['iso']['maximum'], 3200)
        self.assertNotIn('flash_power', schema['properties'])
        self.assertEqual(self.call('/v1/captures', {'controls': {'iso': 50}})[0], 400)
        self.assertEqual(self.call('/v1/captures', {'controls': {'iso': True}})[0], 400)
        self.assertEqual(self.call('/v1/captures', {'controls': {'unknown': 1}})[0], 400)
        self.assertEqual(self.call('/v1/captures', {'camera': 'front', 'controls': {'iso': 400}})[0], 400)
        self.assertEqual(self.call('/v1/captures', {'controls': {'manual_focus_position': 500}})[0], 400)
        _, job = self.call('/v1/preview', {'controls': {'iso': 400, 'exposure_time_us': 8000}})
        command = self.call('/device/next', role='device', raw=True)[1].decode().split('\n')
        self.assertEqual(command[6], 'exposure_time_us=8000;iso=400')
        headers = {'X-Camera-Focus-Status': 'skipped', 'X-Camera-Focus-Range': 'unchanged',
                   'X-Camera-Applied-Controls': '{"iso":400,"exposure_time_us":8000}'}
        self.assertEqual(self.call('/device/result/' + job['id'], jpeg(), role='device', extra_headers=headers)[0], 200)
        self.assertEqual(self.call('/v1/jobs/' + job['id'])[1]['image']['applied_controls']['iso'], 400)

    def test_focus_region_is_validated_sent_and_persisted(self):
        self.register(protocol_version=3)
        self.call('/device/capabilities', capability_fixture(), role='device')
        region = dict(x=0.25, y=0.25, width=0.5, height=0.5)
        self.assertEqual(self.call('/v1/preview', {'focus': False, 'focus_region': region})[0], 400)
        self.assertEqual(self.call('/v1/preview', {'focus': True, 'focus_region': dict(region, width=1)})[0], 400)
        _, job = self.call('/v1/preview', {'focus': True, 'focus_region': region})
        command = self.call('/device/next', role='device', raw=True)[1].decode().split('\n')
        self.assertEqual(command[7], '0.25,0.25,0.5,0.5')
        headers = {'X-Camera-Focus-Status': 'locked', 'X-Camera-Focus-Attempts': '1'}
        self.assertEqual(self.call('/device/result/' + job['id'], jpeg(), role='device', extra_headers=headers)[0], 200)
        image = self.call('/v1/jobs/' + job['id'])[1]['image']
        self.assertEqual(State(self.temp.name, self.config).images[image['id']]['focus_region'], region)

    def test_capability_sessions_and_invalid_reports(self):
        self.register(protocol_version=3)
        previous = self.session
        self.call('/device/capabilities', capability_fixture(), role='device')
        self.register(protocol_version=3)
        self.assertFalse(self.call('/v1/capabilities')[1]['ready'])
        self.assertEqual(self.call('/device/capabilities', capability_fixture(), role='device', session=previous)[0], 409)
        self.assertEqual(self.call('/device/capabilities', {'version': 1, 'cameras': ['bad']}, role='device')[0], 400)
        self.assertEqual(self.call('/v1/capabilities', role=None)[0], 401)

    def test_exif_reports_actual_exposure_without_changing_original(self):
        self.register()
        job = self.acquire()
        output = io.BytesIO()
        exif = Image.Exif()
        exif[34665] = {33434: 0.008, 34855: 400}
        Image.new('RGB', (640, 480)).save(output, 'JPEG', exif=exif)
        original = output.getvalue()
        self.call('/device/result/' + job['id'], original, role='device')
        image = self.call('/v1/jobs/' + job['id'])[1]['image']
        self.assertEqual(image['iso'], 400)
        self.assertAlmostEqual(image['exposure_seconds'], 0.008, places=4)
        self.assertEqual(self.call(image['url'], raw=True)[1], original)


if __name__ == '__main__':
    unittest.main()
