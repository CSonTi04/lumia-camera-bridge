using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using Windows.Phone.Media.Capture;

namespace LumiaAgent
{
    [DataContract] public sealed class ControlChoice
    {
        [DataMember] public object value;
        [DataMember] public string label;
    }
    [DataContract] public sealed class ControlCapability
    {
        [DataMember] public string name;
        [DataMember] public string value_type;
        [DataMember] public string native_type;
        [DataMember] public string unit;
        [DataMember] public bool supported;
        [DataMember] public bool nullable;
        [DataMember] public double? minimum;
        [DataMember] public double? maximum;
        [DataMember] public List<ControlChoice> choices = new List<ControlChoice>();
    }
    [DataContract] public sealed class CameraCapability
    {
        [DataMember] public string camera;
        [DataMember] public bool autofocus_supported;
        [DataMember] public bool focus_region_supported;
        [DataMember] public List<string> focus_ranges = new List<string>();
        [DataMember] public string focus_region_coordinates = "normalized unrotated preview: x,y,width,height in 0..1";
        [DataMember] public List<ControlCapability> controls = new List<ControlCapability>();
    }
    [DataContract] public sealed class CapabilityReport
    {
        [DataMember] public int version = 1;
        [DataMember] public List<CameraCapability> cameras = new List<CameraCapability>();
    }

    internal sealed class ControlDefinition
    {
        public string Name, Unit;
        public Guid Property;
        public Type NativeType;
        public bool Nullable, BeforeFocus;
        public ControlDefinition(string name, Guid property, Type type, string unit, bool nullable = false, bool beforeFocus = false)
        { Name = name; Property = property; NativeType = type; Unit = unit; Nullable = nullable; BeforeFocus = beforeFocus; }
    }

    internal static class CameraControls
    {
        internal static readonly ControlDefinition[] Definitions = {
            new ControlDefinition("iso", KnownCameraPhotoProperties.Iso, typeof(UInt32), "ISO", true),
            new ControlDefinition("exposure_time_us", KnownCameraPhotoProperties.ExposureTime, typeof(UInt32), "microseconds", true),
            new ControlDefinition("exposure_compensation", KnownCameraPhotoProperties.ExposureCompensation, typeof(Int32), "1/6 EV"),
            new ControlDefinition("white_balance_kelvin", KnownCameraPhotoProperties.ManualWhiteBalance, typeof(UInt32), "kelvin", true),
            new ControlDefinition("white_balance_preset", KnownCameraPhotoProperties.WhiteBalancePreset, typeof(WhiteBalancePreset), "preset", true),
            new ControlDefinition("scene_mode", KnownCameraPhotoProperties.SceneMode, typeof(CameraSceneMode), "preset", false, true),
            new ControlDefinition("flash_mode", KnownCameraPhotoProperties.FlashMode, typeof(FlashState), "mode"),
            new ControlDefinition("flash_power", KnownCameraPhotoProperties.FlashPower, typeof(UInt32), "device units"),
            new ControlDefinition("focus_illumination_mode", KnownCameraPhotoProperties.FocusIlluminationMode, typeof(FocusIlluminationMode), "mode", false, true),
            new ControlDefinition("manual_focus_position", KnownCameraGeneralProperties.ManualFocusPosition, typeof(UInt32), "device lens units"),
            new ControlDefinition("auto_lock", KnownCameraPhotoProperties.LockedAutoFocusParameters, typeof(AutoFocusParameters), "bit flags: focus=1 exposure=2 white_balance=4"),
            new ControlDefinition("encode_orientation_degrees", KnownCameraGeneralProperties.EncodeWithOrientation, typeof(Int32), "degrees", false, true),
            new ControlDefinition("capture_orientation_degrees", KnownCameraGeneralProperties.SpecifiedCaptureOrientation, typeof(Int32), "degrees", false, true),
            new ControlDefinition("shutter_sound", KnownCameraGeneralProperties.PlayShutterSoundOnCapture, typeof(Boolean), "boolean", false, true)
        };

        internal static object JsonValue(object value)
        {
            if (value == null) return null;
            if (value is bool) return value;
            return Convert.ToInt64(value, CultureInfo.InvariantCulture);
        }

        internal static ControlCapability Describe(CameraSensorLocation sensor, ControlDefinition def)
        {
            var result = new ControlCapability { name = def.Name, value_type = def.NativeType == typeof(Boolean) ? "boolean" : "integer", unit = def.Unit, nullable = def.Nullable };
            try
            {
                var values = PhotoCaptureDevice.GetSupportedPropertyValues(sensor, def.Property);
                foreach (object value in values)
                {
                    if (value != null) result.native_type = value.GetType().FullName;
                    string label = def.NativeType.IsEnum ? Enum.ToObject(def.NativeType, Convert.ToInt32(value)).ToString() : Convert.ToString(value, CultureInfo.InvariantCulture);
                    result.choices.Add(new ControlChoice { value = JsonValue(value), label = label });
                }
                result.supported = result.choices.Count > 0;
            }
            catch { }
            if (def.Name == "auto_lock" && result.choices.Count > 0)
            {
                int mask = result.choices.Aggregate(0, (value, choice) => value | Convert.ToInt32(choice.value));
                result.choices.Clear();
                for (int value = 0; value <= 7; value++)
                    if ((value & ~mask) == 0) result.choices.Add(new ControlChoice { value = (Int64)value, label = ((AutoFocusParameters)value).ToString() });
            }
            try
            {
                var range = PhotoCaptureDevice.GetSupportedPropertyRange(sensor, def.Property);
                if (range.Min != null) result.native_type = range.Min.GetType().FullName;
                result.minimum = Convert.ToDouble(range.Min, CultureInfo.InvariantCulture);
                result.maximum = Convert.ToDouble(range.Max, CultureInfo.InvariantCulture);
                result.supported = true;
            }
            catch { }
            if (result.choices.Count == 0 && result.minimum.HasValue && result.minimum == result.maximum)
                result.supported = false; // A 0..0 sentinel does not provide an adjustable control.
            if (def.Name == "manual_focus_position" && !PhotoCaptureDevice.IsFocusSupported(sensor))
                result.supported = false;
            return result;
        }

        public static byte[] CapabilityJson()
        {
            var report = new CapabilityReport();
            foreach (var sensor in PhotoCaptureDevice.AvailableSensorLocations)
            {
                var info = new CameraCapability { camera = sensor == CameraSensorLocation.Back ? "rear" : "front", autofocus_supported = PhotoCaptureDevice.IsFocusSupported(sensor), focus_region_supported = PhotoCaptureDevice.IsFocusRegionSupported(sensor) };
                if (info.autofocus_supported)
                    try { info.focus_ranges = PhotoCaptureDevice.GetSupportedPropertyValues(sensor, KnownCameraGeneralProperties.AutoFocusRange).Select(value => ((AutoFocusRange)Convert.ToInt32(value)).ToString().ToLowerInvariant()).ToList(); } catch { }
                foreach (var def in Definitions) info.controls.Add(Describe(sensor, def));
                report.cameras.Add(info);
            }
            using (var stream = new MemoryStream())
            {
                new DataContractJsonSerializer(typeof(CapabilityReport)).WriteObject(stream, report);
                return stream.ToArray();
            }
        }

        public static Dictionary<string, string> Parse(string wire)
        {
            var result = new Dictionary<string, string>();
            if (String.IsNullOrEmpty(wire)) return result;
            foreach (string part in wire.Split(';'))
            {
                string[] pair = part.Split(new[] { '=' }, 2);
                if (pair.Length != 2 || !Definitions.Any(d => d.Name == pair[0]) || result.ContainsKey(pair[0]))
                    throw new InvalidOperationException("Invalid camera control command");
                result.Add(pair[0], pair[1]);
            }
            return result;
        }

        internal static object NativeValue(ControlDefinition def, string text)
        {
            if (text == "null")
            {
                if (!def.Nullable) throw new InvalidOperationException("Control cannot use auto/null: " + def.Name);
                return null;
            }
            if (def.NativeType.IsEnum) return Enum.ToObject(def.NativeType, Int32.Parse(text, CultureInfo.InvariantCulture));
            return Convert.ChangeType(text, def.NativeType, CultureInfo.InvariantCulture);
        }

        internal static string JsonLiteral(object value)
        {
            if (value == null) return "null";
            if (value is bool) return (bool)value ? "true" : "false";
            return Convert.ToString(JsonValue(value), CultureInfo.InvariantCulture);
        }
    }

    internal sealed class CameraControlScope : IDisposable
    {
        readonly PhotoCaptureDevice device;
        readonly Dictionary<string, string> requested;
        readonly List<KeyValuePair<ControlDefinition, object>> restore = new List<KeyValuePair<ControlDefinition, object>>();
        readonly Dictionary<string, object> applied = new Dictionary<string, object>();
        readonly Windows.Foundation.Rect? oldRegion;
        public bool RestoreFailed { get; private set; }

        public CameraControlScope(PhotoCaptureDevice device, Dictionary<string, string> requested)
        { this.device = device; this.requested = requested; oldRegion = PhotoCaptureDevice.IsFocusRegionSupported(device.SensorLocation) ? device.FocusRegion : null; }

        public void SetFocusRegion(string wire)
        {
            if (!PhotoCaptureDevice.IsFocusRegionSupported(device.SensorLocation))
            {
                if (!String.IsNullOrEmpty(wire)) throw new InvalidOperationException("Focus regions are unavailable on this camera");
                return;
            }
            if (String.IsNullOrEmpty(wire)) { device.FocusRegion = null; return; }
            double[] values = wire.Split(',').Select(v => Double.Parse(v, CultureInfo.InvariantCulture)).ToArray();
            if (values.Length != 4 || values.Any(v => Double.IsNaN(v) || Double.IsInfinity(v)) || values[0] < 0 || values[1] < 0 || values[2] <= 0 || values[3] <= 0 || values[0] + values[2] > 1 || values[1] + values[3] > 1)
                throw new InvalidOperationException("Invalid normalized focus region");
            device.FocusRegion = new Windows.Foundation.Rect(values[0] * device.PreviewResolution.Width, values[1] * device.PreviewResolution.Height, values[2] * device.PreviewResolution.Width, values[3] * device.PreviewResolution.Height);
        }

        void Set(ControlDefinition def, object value)
        {
            string stage = "read baseline";
            try
            {
                if (!restore.Any(item => item.Key.Name == def.Name)) restore.Add(new KeyValuePair<ControlDefinition, object>(def, device.GetProperty(def.Property)));
                stage = "apply";
                device.SetProperty(def.Property, value);
                stage = "read result";
                applied[def.Name] = device.GetProperty(def.Property);
            }
            catch (Exception error)
            {
                throw new InvalidOperationException("Camera control '" + def.Name + "' failed to " + stage + ": " + error.GetType().Name + " " + error.Message, error);
            }
        }

        public void Apply(bool beforeFocus, bool focusLocked)
        {
            foreach (var def in CameraControls.Definitions.Where(d => d.BeforeFocus == beforeFocus && requested.ContainsKey(d.Name)))
            {
                object value = CameraControls.NativeValue(def, requested[def.Name]);
                if (def.Name == "shutter_sound" && value is bool && !(bool)value)
                {
                    if (Convert.ToBoolean(device.GetProperty(KnownCameraGeneralProperties.IsShutterSoundRequiredForRegion)))
                        throw new InvalidOperationException("The device requires a shutter sound in this region");
                }
                if (def.Name == "auto_lock" && focusLocked) value = (AutoFocusParameters)(Convert.ToInt32(value) | (int)AutoFocusParameters.Focus);
                if (def.Name == "manual_focus_position")
                {
                    var lockDef = CameraControls.Definitions.First(d => d.Name == "auto_lock");
                    Set(lockDef, (AutoFocusParameters)(Convert.ToInt32(device.GetProperty(lockDef.Property)) | (int)AutoFocusParameters.Focus));
                    var nativeType = CameraControls.Describe(device.SensorLocation, def).native_type;
                    if (nativeType == "System.Int32") value = Convert.ToInt32(value);
                }
                Set(def, value);
            }
            if (!beforeFocus && requested.ContainsKey("manual_focus_position"))
            {
                var def = CameraControls.Definitions.First(d => d.Name == "auto_lock");
                Set(def, (AutoFocusParameters)(Convert.ToInt32(device.GetProperty(def.Property)) | (int)AutoFocusParameters.Focus));
            }
        }

        public string AppliedJson()
        {
            return "{" + String.Join(",", applied.Select(item => "\"" + item.Key + "\":" + CameraControls.JsonLiteral(item.Value))) + "}";
        }

        public void Dispose()
        {
            for (int i = restore.Count - 1; i >= 0; i--)
            {
                try { device.SetProperty(restore[i].Key.Property, restore[i].Value); }
                catch (Exception error) { RestoreFailed = true; AppLog.Write("Control restore failed " + restore[i].Key.Name + " " + error.GetType().FullName); }
            }
            try { if (PhotoCaptureDevice.IsFocusRegionSupported(device.SensorLocation)) device.FocusRegion = oldRegion; }
            catch { RestoreFailed = true; }
        }
    }
}
