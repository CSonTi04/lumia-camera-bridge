"""Phone-reported control capabilities, request validation and OpenAPI schemas."""
import copy
import math

CONTROL_NAMES = {
    'iso', 'exposure_time_us', 'exposure_compensation', 'white_balance_kelvin',
    'white_balance_preset', 'scene_mode', 'flash_mode', 'flash_power',
    'focus_illumination_mode', 'manual_focus_position', 'auto_lock',
    'encode_orientation_degrees', 'capture_orientation_degrees', 'shutter_sound',
}


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def clean_capabilities(report):
    if not isinstance(report, dict) or type(report.get('version')) is not int or report.get('version') != 1:
        raise ValueError('Unsupported capability report')
    cameras = report.get('cameras')
    if not isinstance(cameras, list) or not 1 <= len(cameras) <= 2:
        raise ValueError('Expected rear/front camera capability records')
    result = []
    for camera in cameras:
        if not isinstance(camera, dict):
            raise ValueError('Invalid camera record')
        name = camera.get('camera')
        if name not in ('rear', 'front') or any(item['camera'] == name for item in result):
            raise ValueError('Invalid or duplicate camera')
        controls = camera.get('controls')
        if not isinstance(controls, list) or len(controls) > len(CONTROL_NAMES):
            raise ValueError('Invalid camera control list')
        clean = []
        for control in controls:
            if not isinstance(control, dict):
                raise ValueError('Invalid control record')
            key = control.get('name')
            if key not in CONTROL_NAMES or any(item['name'] == key for item in clean):
                raise ValueError('Invalid or duplicate control')
            kind = 'boolean' if key == 'shutter_sound' else 'integer'
            if control.get('value_type') != kind:
                raise ValueError('Invalid control type')
            low, high = control.get('minimum'), control.get('maximum')
            if any(v is not None and not finite_number(v) for v in (low, high)) or (low is not None and high is not None and low > high):
                raise ValueError('Invalid control bounds')
            choices = control.get('choices', [])
            if not isinstance(choices, list) or len(choices) > 256:
                raise ValueError('Invalid control choices')
            cleaned_choices = []
            for choice in choices:
                if not isinstance(choice, dict):
                    raise ValueError('Invalid choice record')
                value = choice.get('value')
                if type(value) is not (bool if kind == 'boolean' else int):
                    raise ValueError('Invalid control choice type')
                cleaned_choices.append(dict(value=value, label=str(choice.get('label', value))[:80]))
            clean.append(dict(name=key, value_type=kind, unit=str(control.get('unit', ''))[:100],
                              supported=control.get('supported') is True, nullable=control.get('nullable') is True,
                              minimum=low, maximum=high, choices=cleaned_choices))
        focus_ranges = camera.get('focus_ranges', [])
        if not isinstance(focus_ranges, list) or len(focus_ranges) > 5 or any(value not in ('normal', 'macro', 'full', 'infinity', 'hyperfocal') for value in focus_ranges):
            raise ValueError('Invalid focus ranges')
        result.append(dict(camera=name, autofocus_supported=camera.get('autofocus_supported') is True, focus_ranges=focus_ranges,
                           focus_region_supported=camera.get('focus_region_supported') is True,
                           focus_region_coordinates='normalized unrotated preview, 0..1', controls=clean))
    return dict(version=1, cameras=result)


def validate_request(params, camera, focus, protocol, capabilities):
    controls = params.get('controls', {})
    region = params.get('focus_region')
    if not isinstance(controls, dict) or len(controls) > len(CONTROL_NAMES):
        raise ValueError('controls must be a bounded object')
    if controls or region is not None:
        if protocol < 3 or capabilities is None:
            raise ValueError('Controls require Lumia Agent 0.1.9+ and a ready capability report')
    sensor = next((item for item in (capabilities or {}).get('cameras', []) if item['camera'] == camera), None)
    requested_range = params.get('focus_range', 'auto')
    if sensor and sensor.get('focus_ranges') and requested_range != 'auto' and requested_range not in sensor['focus_ranges']:
        raise ValueError('Unsupported focus range on this camera')
    catalog = {item['name']: item for item in sensor['controls']} if sensor else {}
    for name, value in controls.items():
        entry = catalog.get(name)
        if not entry or not entry['supported']:
            raise ValueError('Unsupported control on this camera: ' + name)
        if value is None:
            if not entry['nullable']:
                raise ValueError('Control does not support auto/null: ' + name)
            continue
        expected = bool if entry['value_type'] == 'boolean' else int
        if type(value) is not expected:
            raise ValueError('Wrong value type for control: ' + name)
        if entry['choices'] and value not in [choice['value'] for choice in entry['choices']]:
            raise ValueError('Unsupported choice for control: ' + name)
        if expected is int and ((entry['minimum'] is not None and value < entry['minimum']) or (entry['maximum'] is not None and value > entry['maximum'])):
            raise ValueError('Value outside camera-reported range: ' + name)
    if 'manual_focus_position' in controls and focus:
        raise ValueError('manual_focus_position requires focus=false')
    if controls.get('white_balance_kelvin') is not None and controls.get('white_balance_preset') is not None:
        raise ValueError('Choose white_balance_kelvin or white_balance_preset')
    if region is not None:
        if not focus or not sensor or not sensor['focus_region_supported']:
            raise ValueError('focus_region requires focus=true and a capable camera')
        if not isinstance(region, dict) or set(region) != {'x', 'y', 'width', 'height'}:
            raise ValueError('focus_region needs x,y,width,height')
        x, y, w, h = (region[key] for key in ('x', 'y', 'width', 'height'))
        if not all(finite_number(v) for v in (x, y, w, h)) or x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1 or y + h > 1:
            raise ValueError('focus_region must fit normalized preview coordinates 0..1')
    return controls, region


def wire_controls(controls):
    def value(item):
        return 'null' if item is None else str(item).lower() if type(item) is bool else str(item)
    return ';'.join(name + '=' + value(item) for name, item in sorted(controls.items()))


def wire_region(region):
    return '' if region is None else ','.join(format(region[key], '.17g') for key in ('x', 'y', 'width', 'height'))


def applied_metadata(payload):
    if not isinstance(payload, dict) or len(payload) > len(CONTROL_NAMES):
        raise ValueError('Invalid applied control metadata')
    for key, value in payload.items():
        if key not in CONTROL_NAMES or (value is not None and type(value) not in (bool, int)):
            raise ValueError('Invalid applied control metadata')
    return payload


def openapi_with_controls(spec, capabilities):
    spec = copy.deepcopy(spec)
    if not capabilities:
        return spec
    properties = {}
    rear = next((camera for camera in capabilities['cameras'] if camera['camera'] == 'rear'), None)
    if rear and rear.get('focus_ranges'):
        spec['components']['schemas']['CameraRequest']['properties']['focus_range']['enum'] = ['auto'] + rear['focus_ranges']
    for camera in capabilities['cameras']:
        for entry in camera['controls']:
            if not entry['supported'] or entry['name'] in properties:
                continue
            schema = dict(type=entry['value_type'], nullable=entry['nullable'], description='Units: ' + entry['unit'] + '. Sensor support and limits: GET /v1/capabilities.')
            if entry['choices']:
                schema['enum'] = [item['value'] for item in entry['choices']] + ([None] if entry['nullable'] else [])
                schema['description'] += ' Choices: ' + ', '.join(str(item['value']) + '=' + item['label'] for item in entry['choices'])
            if entry['value_type'] == 'integer':
                for field, value in (('minimum', entry['minimum']), ('maximum', entry['maximum'])):
                    if value is not None:
                        schema[field] = value
            properties[entry['name']] = schema
    spec['components']['schemas']['CameraRequest']['properties']['controls'] = dict(type='object', additionalProperties=False, properties=properties, description='Per-request native controls; omitted controls retain their current baseline. Overrides are restored after acquisition. null selects auto where supported. Manual focus requires focus=false.')
    return spec
