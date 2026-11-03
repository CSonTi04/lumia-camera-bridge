using System;
using System.IO;
using System.IO.IsolatedStorage;
using System.Linq;
using System.Net;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Navigation;
using System.Windows.Threading;
using Microsoft.Phone.Controls;
using Microsoft.Devices;
using Microsoft.Phone.Info;
using Microsoft.Phone.Shell;
using Windows.Phone.Media.Capture;
using WSize = Windows.Foundation.Size;

namespace LumiaAgent
{
    [DataContract]
    public class Registration
    {
        [DataMember] public string model;
        [DataMember] public string os;
        [DataMember] public string app_version;
        [DataMember] public int protocol_version = 3;
    }

    public class MainPage : PhoneApplicationPage
    {
        readonly TextBox address = new TextBox { Text = "http://raspberrypi.local:8765" };
        readonly PasswordBox token = new PasswordBox();
        readonly TextBlock status = new TextBlock { Text = "Enter the Pi URL and device token.", TextWrapping = TextWrapping.Wrap, FontSize = 22 };
        readonly Button connect = new Button { Content = "Connect camera" };
        readonly Button previewToggle = new Button { Content = "Show live preview" };
        readonly VideoBrush viewfinder = new VideoBrush { Stretch = Stretch.Uniform };
        readonly Border viewfinderHost = new Border();
        readonly TextBlock previewPlaceholder = new TextBlock { Text = "Live preview is off.\nAgent camera commands are available when connected.", TextWrapping = TextWrapping.Wrap, FontSize = 22, VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
        readonly SemaphoreSlim cameraAccess = new SemaphoreSlim(1, 1);
        readonly TextBlock title = new TextBlock { Text = "LUMIA AGENT 0.1.12", FontSize = 36 };
        readonly Button blackScreen = new Button { Content = "Black screen now" };
        readonly CheckBox autoBlack = new CheckBox { Content = "OLED protection: black after 30 seconds", IsChecked = true };
        readonly Grid screen = new Grid();
        readonly Border blackOverlay = new Border { Background = new SolidColorBrush(Colors.Black), Visibility = Visibility.Collapsed };
        readonly DispatcherTimer oledTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(30) };
        readonly Grid layout = new Grid();
        readonly Grid cameraPanel = new Grid();
        PhotoCaptureDevice camera;
        string currentCamera, currentAspect, endpoint, secret, session;
        int generation;
        int cameraEpoch;
        bool running;
        bool previewEnabled;
        bool initialLoad;
        bool shutterAttached;
        bool capabilitiesSent;

        public MainPage()
        {
            AppLog.Write("MainPage constructor");
            SupportedOrientations = SupportedPageOrientation.PortraitOrLandscape;
            SystemTray.SetIsVisible(this, false);
            AppLog.Write("Page tray hidden");
            var panel = new StackPanel { Margin = new Thickness(12) };
            panel.Children.Add(title);
            panel.Children.Add(new TextBlock { Text = "Raspberry Pi bridge URL" });
            panel.Children.Add(address);
            panel.Children.Add(new TextBlock { Text = "Device token (from Pi config.json)" });
            panel.Children.Add(token);
            panel.Children.Add(connect);
            panel.Children.Add(previewToggle);
            panel.Children.Add(blackScreen);
            panel.Children.Add(autoBlack);
            panel.Children.Add(new TextBlock { Text = "Wake the black screen with the camera button or a tap anywhere.", TextWrapping = TextWrapping.Wrap, FontSize = 18 });
            panel.Children.Add(new TextBlock { Text = "Camera access is active while this app stays open.\nKeep the phone powered and on the same Wi-Fi as the Pi.", TextWrapping = TextWrapping.Wrap, FontSize = 18 });
            layout.RowDefinitions.Add(new RowDefinition());
            layout.RowDefinitions.Add(new RowDefinition());
            layout.ColumnDefinitions.Add(new ColumnDefinition());
            layout.ColumnDefinitions.Add(new ColumnDefinition());
            layout.Children.Add(new ScrollViewer { Content = panel });
            cameraPanel.Margin = new Thickness(12);
            cameraPanel.RowDefinitions.Add(new RowDefinition());
            cameraPanel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            viewfinderHost.Background = viewfinder;
            cameraPanel.Children.Add(viewfinderHost);
            cameraPanel.Children.Add(previewPlaceholder);
            Grid.SetRow(status, 1);
            cameraPanel.Children.Add(status);
            layout.Children.Add(cameraPanel);
            screen.Children.Add(layout);
            screen.Children.Add(blackOverlay);
            Content = screen;
            ApplyOrientation(Orientation);
            UpdatePreviewDisplay();
            try { PairingConfig.Import(); }
            catch (Exception error) {
                AppLog.Write("Pairing import failed " + error.GetType().FullName);
                status.Text = "Could not import pairing. Enter the Pi address and device token below.";
            }
            var settings = IsolatedStorageSettings.ApplicationSettings;
            if (settings.Contains("address")) address.Text = (string)settings["address"];
            if (settings.Contains("device_token")) token.Password = (string)settings["device_token"];
            if (settings.Contains("oled_auto_black")) autoBlack.IsChecked = (bool)settings["oled_auto_black"];
            connect.Click += Connect;
            previewToggle.Click += TogglePreview;
            blackScreen.Click += (s, e) => ProtectScreen();
            oledTimer.Tick += (s, e) => ProtectScreen();
            blackOverlay.MouseLeftButtonUp += (s, e) => { e.Handled = true; WakeScreen(); };
            AddHandler(UIElement.MouseLeftButtonDownEvent, new MouseButtonEventHandler((s, e) => ResetOledTimer()), true);
            RoutedEventHandler saveOled = (s, e) => {
                settings["oled_auto_black"] = autoBlack.IsChecked == true;
                settings.Save();
                WakeScreen();
            };
            autoBlack.Checked += saveOled;
            autoBlack.Unchecked += saveOled;
            // Release camera on backgrounding; WP does not permit an ordinary background camera service.
            var service = PhoneApplicationService.Current;
            service.Deactivated += (s, e) => Stop();
            service.Closing += (s, e) => Stop();
            Loaded += (s, e) => {
                AppLog.Write("MainPage loaded");
                ApplyOrientation(Orientation);
                if (initialLoad) return;
                initialLoad = true;
                if (settings.Contains("connect_on_launch") && (bool)settings["connect_on_launch"])
                    Connect(null, null);
            };
            AppLog.Write("MainPage initialized");
        }

        protected override void OnOrientationChanged(OrientationChangedEventArgs e)
        {
            base.OnOrientationChanged(e);
            ApplyOrientation(e.Orientation);
        }

        void ApplyOrientation(PageOrientation orientation)
        {
            bool landscape = (orientation & PageOrientation.Landscape) != 0;
            layout.RowDefinitions[0].Height = new GridLength(1, GridUnitType.Star);
            layout.RowDefinitions[1].Height = landscape ? new GridLength(0) : new GridLength(1, GridUnitType.Star);
            layout.ColumnDefinitions[0].Width = new GridLength(landscape ? 0.9 : 1, GridUnitType.Star);
            layout.ColumnDefinitions[1].Width = landscape ? new GridLength(1.1, GridUnitType.Star) : new GridLength(0);
            Grid.SetRow(cameraPanel, landscape ? 0 : 1);
            Grid.SetColumn(cameraPanel, landscape ? 1 : 0);
            title.FontSize = landscape ? 28 : 36;
        }

        protected override void OnNavigatedFrom(NavigationEventArgs e)
        {
            if (shutterAttached)
            {
                CameraButtons.ShutterKeyHalfPressed -= WakeFromCameraButton;
                CameraButtons.ShutterKeyPressed -= WakeFromCameraButton;
                shutterAttached = false;
            }
            Stop();
            base.OnNavigatedFrom(e);
        }

        protected override void OnNavigatedTo(NavigationEventArgs e)
        {
            base.OnNavigatedTo(e);
            if (!shutterAttached)
            {
                CameraButtons.ShutterKeyHalfPressed += WakeFromCameraButton;
                CameraButtons.ShutterKeyPressed += WakeFromCameraButton;
                shutterAttached = true;
            }
        }

        void WakeFromCameraButton(object sender, EventArgs e)
        {
            Dispatcher.BeginInvoke(() => { WakeScreen(); AppLog.Write("Camera button wake"); });
        }

        void ResetOledTimer()
        {
            oledTimer.Stop();
            if (blackOverlay.Visibility != Visibility.Visible && autoBlack.IsChecked == true && (running || previewEnabled))
                oledTimer.Start();
        }

        void ProtectScreen()
        {
            oledTimer.Stop();
            // No text or wake target is drawn: every app pixel is black.
            blackOverlay.Visibility = Visibility.Visible;
            viewfinderHost.Visibility = Visibility.Collapsed;
            AppLog.Write("OLED black screen");
        }

        void WakeScreen()
        {
            blackOverlay.Visibility = Visibility.Collapsed;
            UpdatePreviewDisplay();
        }

        void Stop()
        {
            running = false;
            generation++;
            cameraEpoch++;
            previewEnabled = false;
            if (camera != null) { camera.Dispose(); camera = null; }
            currentCamera = currentAspect = null;
            connect.Content = "Connect camera";
            address.IsEnabled = token.IsEnabled = true;
            blackOverlay.Visibility = Visibility.Collapsed;
            UpdatePreviewDisplay();
        }

        void UpdatePreviewDisplay()
        {
            viewfinderHost.Visibility = previewEnabled && blackOverlay.Visibility != Visibility.Visible ? Visibility.Visible : Visibility.Collapsed;
            previewPlaceholder.Visibility = previewEnabled ? Visibility.Collapsed : Visibility.Visible;
            previewToggle.Content = previewEnabled ? "Hide live preview" : "Show live preview";
            PhoneApplicationService.Current.UserIdleDetectionMode = (running || previewEnabled) ? IdleDetectionMode.Disabled : IdleDetectionMode.Enabled;
            ResetOledTimer();
        }

        async void TogglePreview(object sender, RoutedEventArgs e)
        {
            previewEnabled = !previewEnabled;
            UpdatePreviewDisplay();
            if (!previewEnabled)
            {
                AppLog.Write("Local preview hidden");
                if (!running && cameraAccess.Wait(0))
                {
                    try
                    {
                        if (camera != null) { camera.Dispose(); camera = null; }
                        currentCamera = currentAspect = null;
                    }
                    finally { cameraAccess.Release(); }
                }
                return;
            }
            int epoch = cameraEpoch;
            previewToggle.IsEnabled = false;
            try
            {
                await cameraAccess.WaitAsync();
                try
                {
                    if (epoch != cameraEpoch) return;
                    await OpenCamera(currentCamera ?? "rear", currentAspect ?? "4:3", epoch);
                    AppLog.Write("Local preview enabled");
                }
                finally { cameraAccess.Release(); }
            }
            catch (Exception error)
            {
                if (epoch == cameraEpoch)
                {
                    previewEnabled = false;
                    status.Text = "Preview error: " + error.Message;
                    AppLog.Write("Local preview error " + error.GetType().FullName);
                }
            }
            finally { previewToggle.IsEnabled = true; UpdatePreviewDisplay(); }
        }

        async void Connect(object sender, RoutedEventArgs e)
        {
            if (running) { Stop(); status.Text = "Disconnected."; return; }
            Uri uri;
            if (!PairingConfig.IsBridgeOrigin(address.Text.Trim().TrimEnd('/'), out uri))
            {
                status.Text = "Use an HTTP bridge origin, e.g. http://raspberrypi.local:8765";
                return;
            }
            if (token.Password.Trim().Length < 24) { status.Text = "Enter the device token from config.json."; return; }
            endpoint = uri.Scheme + "://" + uri.Authority;
            secret = token.Password.Trim();
            var settings = IsolatedStorageSettings.ApplicationSettings;
            settings["address"] = endpoint;
            settings["device_token"] = secret;
            settings.Save();
            running = true;
            AppLog.Write("Connecting");
            int mine = ++generation;
            address.IsEnabled = token.IsEnabled = false;
            connect.Content = "Disconnect camera";
            PhoneApplicationService.Current.UserIdleDetectionMode = IdleDetectionMode.Disabled;
            ResetOledTimer();
            session = null;
            capabilitiesSent = false;
            while (running && mine == generation)
            {
                bool retry = false;
                try
                {
                    if (session == null)
                    {
                        status.Text = "Connecting to Pi...";
                        var info = new Registration { model = DeviceStatus.DeviceName, os = System.Environment.OSVersion.Version.ToString(), app_version = "0.1.12" };
                        using (var buffer = new MemoryStream())
                        {
                            new DataContractJsonSerializer(typeof(Registration)).WriteObject(buffer, info);
                            session = Encoding.UTF8.GetString(await Request("POST", "/device/register", buffer.ToArray(), "application/json"), 0, 32).Trim();
                            AppLog.Write("Registered with bridge");
                            capabilitiesSent = false;
                        }
                    }
                    if (!capabilitiesSent)
                    {
                        await Request("POST", "/device/capabilities", CameraControls.CapabilityJson(), "application/json");
                        capabilitiesSent = true;
                        AppLog.Write("Camera capabilities reported");
                    }
                    if (!running || mine != generation) break;
                    status.Text = "Connected. Waiting for an agent command.";
                    byte[] response = await Request("GET", "/device/next", null, null);
                    if (!running || mine != generation) break;
                    string[] command = Encoding.UTF8.GetString(response, 0, response.Length).Split('\n');
                    if (command.Length < 5) continue;
                    string id = command[0].Trim();
                    if (id.Length != 32 || id.Any(c => !Uri.IsHexDigit(c))) throw new InvalidOperationException("Invalid command ID");
                    string cameraError = null;
                    try
                    {
                        string kind = command[1].Trim(), sensor = command[2].Trim(), aspect = command[3].Trim();
                        if ((kind != "preview" && kind != "capture") || (sensor != "rear" && sensor != "front")) throw new InvalidOperationException("Unsupported camera command");
                        status.Text = "Taking " + sensor + " " + kind + "...";
                        AppLog.Write("Camera command " + sensor + " " + kind);
                        CameraImage image;
                        await cameraAccess.WaitAsync();
                        try
                        {
                            if (!running || mine != generation) break;
                            await OpenCamera(sensor, aspect, cameraEpoch);
                            if (!running || mine != generation) break;
                            bool focus = command[4].Trim() == "true";
                            string focusRange = command.Length > 5 ? command[5].Trim() : "auto";
                            var controls = CameraControls.Parse(command.Length > 6 ? command[6].Trim() : "");
                            string region = command.Length > 7 ? command[7].Trim() : "";
                            var scope = new CameraControlScope(camera, controls);
                            try
                            {
                                scope.SetFocusRegion(region);
                                scope.Apply(true, false);
                                if (kind == "preview")
                                {
                                    var result = await FocusCamera(focus, focusRange, () => scope.SetFocusRegion(region));
                                    scope.Apply(false, result.Status == "locked");
                                    if (focus || controls.Count > 0) await Task.Delay(250);
                                    image = new CameraImage { Jpeg = Preview(), Focus = result };
                                }
                                else image = await Capture(focus, focusRange, scope, region);
                                if (controls.ContainsKey("manual_focus_position")) { image.Focus.Status = "manual"; image.Focus.Range = "manual"; }
                                image.AppliedControlsJson = scope.AppliedJson();
                            }
                            finally
                            {
                                scope.Dispose();
                                if (scope.RestoreFailed)
                                {
                                    if (camera != null) { camera.Dispose(); camera = null; }
                                    currentCamera = currentAspect = null;
                                }
                            }
                        }
                        finally { cameraAccess.Release(); }
                        if (!running || mine != generation) break;
                        status.Text = "Uploading " + image.Jpeg.Length + " bytes...";
                        await Request("POST", "/device/result/" + id, image.Jpeg, "image/jpeg", image.Focus, image.AppliedControlsJson);
                        AppLog.Write("Image uploaded");
                    }
                    catch (Exception error)
                    {
                        if (!running || mine != generation) break;
                        cameraError = error.GetType().Name + ": " + (String.IsNullOrEmpty(error.Message) ? "The camera driver did not provide an error message." : error.Message);
                        AppLog.Exception("Camera error", error);
                    }
                    if (cameraError != null)
                    {
                        await Request("POST", "/device/error/" + id, Encoding.UTF8.GetBytes(cameraError), "text/plain");
                        status.Text = "Camera error: " + cameraError;
                    }
                }
                catch (Exception error)
                {
                    AppLog.Write("Connection error " + error.GetType().FullName);
                    status.Text = "Connection error: " + error.Message + "\nRetrying in 3 seconds.";
                    var web = error as WebException;
                    var http = web == null ? null : web.Response as HttpWebResponse;
                    if (http != null && (int)http.StatusCode == 409) session = null;
                    if (http != null && (int)http.StatusCode == 401) { Stop(); status.Text = "Pairing token rejected. Check device_token on the Pi."; break; }
                    retry = true;
                }
                if (retry && running && mine == generation) await Task.Delay(3000);
            }
        }

        async Task OpenCamera(string sensorName, string aspect, int epoch)
        {
            if (epoch != cameraEpoch) throw new OperationCanceledException();
            if (camera != null && currentCamera == sensorName && currentAspect == aspect) return;
            if (camera != null) { camera.Dispose(); camera = null; }
            var sensor = sensorName == "front" ? CameraSensorLocation.Front : CameraSensorLocation.Back;
            if (!PhotoCaptureDevice.AvailableSensorLocations.Contains(sensor)) throw new InvalidOperationException("This camera is unavailable");
            // Lumia 1020 high-res modes may be omitted from GetAvailableCaptureResolutions.
            // Explicitly request Nokia's documented modes; never silently substitute 5 MP.
            PhotoCaptureDevice opened;
            if (sensorName == "rear")
            {
                var size = aspect == "16:9" ? new WSize(7712, 4352) : new WSize(7136, 5360);
                opened = await PhotoCaptureDevice.OpenAsync(sensor, size);
            }
            else
            {
                var size = PhotoCaptureDevice.GetAvailableCaptureResolutions(sensor).OrderByDescending(s => s.Width * s.Height).First();
                opened = await PhotoCaptureDevice.OpenAsync(sensor, size);
            }
            if (epoch != cameraEpoch) { opened.Dispose(); throw new OperationCanceledException(); }
            camera = opened;
            currentCamera = sensorName;
            currentAspect = aspect;
            var previews = PhotoCaptureDevice.GetAvailablePreviewResolutions(sensor);
            var preferred = previews.Where(s => s.Width <= 1280).OrderBy(s => Math.Abs(s.Width / s.Height - camera.CaptureResolution.Width / camera.CaptureResolution.Height)).ThenByDescending(s => s.Width).FirstOrDefault();
            if (preferred.Width > 0) await camera.SetPreviewResolutionAsync(preferred);
            if (epoch != cameraEpoch) throw new OperationCanceledException();
            viewfinder.SetSource(camera);
            await Task.Delay(500);
        }

        byte[] Preview()
        {
            int width = (int)camera.PreviewResolution.Width, height = (int)camera.PreviewResolution.Height;
            var bitmap = new WriteableBitmap(width, height);
            camera.GetPreviewBufferArgb(bitmap.Pixels);
            using (var buffer = new MemoryStream())
            {
                bitmap.SaveJpeg(buffer, width, height, 0, 80);
                return buffer.ToArray();
            }
        }

        static AutoFocusRange RangeValue(string name)
        {
            switch (name)
            {
                case "normal": return AutoFocusRange.Normal;
                case "macro": return AutoFocusRange.Macro;
                case "full": return AutoFocusRange.Full;
                case "infinity": return AutoFocusRange.Infinity;
                case "hyperfocal": return AutoFocusRange.Hyperfocal;
                default: throw new InvalidOperationException("Unknown focus range");
            }
        }

        string[] SupportedFocusRanges()
        {
            try
            {
                var values = PhotoCaptureDevice.GetSupportedPropertyValues(camera.SensorLocation, KnownCameraGeneralProperties.AutoFocusRange);
                return new[] { "normal", "macro", "full", "infinity", "hyperfocal" }
                    .Where(name => values.Any(value => Convert.ToInt32(value) == (int)RangeValue(name))).ToArray();
            }
            catch (Exception error)
            {
                AppLog.Write("Focus range query unavailable " + error.GetType().FullName);
                return new string[0];
            }
        }

        async Task<FocusResult> FocusCamera(bool requested, string requestedRange, Action applyRegion = null)
        {
            if (!requested) return new FocusResult { Status = "skipped", Attempts = 0, Range = "unchanged", SupportedRanges = "" };
            if (!PhotoCaptureDevice.IsFocusSupported(camera.SensorLocation))
                return new FocusResult { Status = "unsupported", Attempts = 0, Range = "fixed", SupportedRanges = "" };

            string[] supported = SupportedFocusRanges();
            string selected = requestedRange;
            if (selected == "auto") selected = supported.Contains("normal") ? "normal" : supported.Contains("full") ? "full" : "device_default";
            if (selected != "device_default" && !supported.Contains(selected))
                throw new InvalidOperationException("Focus range '" + selected + "' is unavailable. Supported: " + String.Join(", ", supported));

            // A previous lock must not turn a new request into a stale-focus capture.
            // Focus remains explicitly locked until the exposure finishes.
            for (int attempt = 1; attempt <= 2; attempt++)
            {
                status.Text = "Focusing (attempt " + attempt + ")...";
                camera.SetProperty(KnownCameraPhotoProperties.LockedAutoFocusParameters, AutoFocusParameters.None);
                await camera.ResetFocusAsync();
                if (applyRegion != null) applyRegion();
                if (selected != "device_default") camera.SetProperty(KnownCameraGeneralProperties.AutoFocusRange, RangeValue(selected));
                var result = await camera.FocusAsync();
                AppLog.Write("Autofocus " + result + " range " + selected + " attempt " + attempt);
                if (result == CameraFocusStatus.Locked)
                {
                    camera.SetProperty(KnownCameraPhotoProperties.LockedAutoFocusParameters, AutoFocusParameters.Focus);
                    return new FocusResult { Status = "locked", Attempts = attempt, Range = selected, SupportedRanges = String.Join(",", supported) };
                }
                if (attempt < 2) await Task.Delay(250);
            }
            throw new InvalidOperationException("Autofocus did not lock after two attempts in range '" + selected + "'. Supported ranges: " + String.Join(", ", supported) + ". Aim at a well-lit, detailed subject and retry. Use focus=false only to keep the current focus position.");
        }

        async Task<CameraImage> Capture(bool focus, string focusRange, CameraControlScope scope, string region)
        {
            using (var stream = new MemoryStream())
            {
                var sequence = camera.CreateCaptureSequence(1);
                sequence.Frames[0].CaptureStream = stream.AsOutputStream();
                await camera.PrepareCaptureSequenceAsync(sequence);
                var result = await FocusCamera(focus, focusRange, () => scope.SetFocusRegion(region));
                scope.Apply(false, result.Status == "locked");
                await sequence.StartCaptureAsync();
                return new CameraImage { Jpeg = stream.ToArray(), Focus = result }; // No 38 MP bitmap on phone.
            }
        }

        async Task<byte[]> Request(string method, string path, byte[] body, string contentType, FocusResult focusResult = null, string appliedControls = null)
        {
            var request = (HttpWebRequest)WebRequest.Create(endpoint + path);
            request.Method = method;
            request.Headers["Authorization"] = "Bearer " + secret;
            if (session != null && path != "/device/register") request.Headers["X-Device-Session"] = session;
            if (focusResult != null)
            {
                request.Headers["X-Camera-Focus-Status"] = focusResult.Status;
                request.Headers["X-Camera-Focus-Attempts"] = focusResult.Attempts.ToString(System.Globalization.CultureInfo.InvariantCulture);
                request.Headers["X-Camera-Focus-Range"] = focusResult.Range;
                if (!String.IsNullOrEmpty(focusResult.SupportedRanges)) request.Headers["X-Camera-Focus-Ranges"] = focusResult.SupportedRanges;
            }
            if (appliedControls != null) request.Headers["X-Camera-Applied-Controls"] = appliedControls;
            // WP's HTTP stack buffers the request and supplies Content-Length.
            if (body != null)
            {
                request.ContentType = contentType;
                using (var output = await Task.Factory.FromAsync<Stream>(request.BeginGetRequestStream, request.EndGetRequestStream, null))
                    await output.WriteAsync(body, 0, body.Length);
            }
            using (var response = (HttpWebResponse)await Task.Factory.FromAsync<WebResponse>(request.BeginGetResponse, request.EndGetResponse, null))
            using (var input = response.GetResponseStream())
            using (var output = new MemoryStream())
            {
                await input.CopyToAsync(output);
                return output.ToArray();
            }
        }
    }
}
