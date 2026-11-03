using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Web.Script.Serialization;
using System.Xml;
using System.Xml.Linq;
using Microsoft.SmartDevice.Connectivity.Interface;
using Microsoft.SmartDevice.MultiTargeting.Connectivity;

class PhoneDeploy
{
    static readonly Guid Product = new Guid("D66C350D-2C68-4C77-91F5-0871A6A44A83");
    static string operation = "initializing";
    static void Print(object value) { Console.WriteLine(new JavaScriptSerializer().Serialize(value)); }
    static bool? Running(IRemoteApplication app) { try { return app.IsRunning(); } catch (NotImplementedException) { return null; } }
    static string FindStoredFile(IRemoteIsolatedStorageFile store, string name)
    {
        foreach (string prefix in new[] { "\\IsolatedStore\\", "", "\\", "\\Local\\" })
        {
            try { if (store.FileExists(prefix + name)) return prefix + name; }
            catch (DirectoryNotFoundException) { }
            catch (FileNotFoundException) { }
        }
        return null;
    }

    [STAThread]
    static int Main(string[] args)
    {
        string action = args.Length == 0 ? "--probe" : args[0];
        if (action == "--help")
        {
            Console.WriteLine("PhoneDeploy --list | --probe | --state | --logs <output.log> | --pair <phone-config.json> | --launch | --stop | --install <LumiaAgent.xap>");
            Console.WriteLine("Only deploys the Lumia Agent product ID; updates an existing installation without uninstalling it.");
            return 0;
        }
        if (action != "--list" && action != "--probe" && action != "--state" && action != "--logs" && action != "--pair" && action != "--launch" && action != "--stop" && action != "--install")
        {
            Print(new { error = "Unknown command; use --help" });
            return 2;
        }
        IDevice device = null;
        try
        {
            // Skip Windows Phone 7 targets; their SDK is not needed for a WP8 Lumia.
            var targets = new MultiTargetingConnectivity(1033, true).GetConnectableDevices(true);
            if (action == "--list")
            {
                Print(targets.Select(d => new { name = d.Name, emulator = d.IsEmulator() }).ToArray());
                return 0;
            }
            var candidates = targets.Where(d => !d.IsEmulator()).ToArray();
            if (candidates.Length != 1)
                throw new InvalidOperationException("Expected one physical Windows Phone target, found " + candidates.Length + ". Use --list to inspect SDK configuration.");
            var target = candidates[0];
            operation = "connect";
            device = target.Connect();
            bool installed = device.IsApplicationInstalled(Product);
            if (action == "--probe")
            {
                Print(new { connected = true, target = target.Name, camera_app_installed = installed });
                return 0;
            }
            if (action != "--install")
            {
                if (!installed) throw new InvalidOperationException("Lumia Agent is not installed");
                var ownApp = device.GetApplication(Product);
                if (action == "--state")
                {
                    Print(new { connected = true, installed = true, running = Running(ownApp), product_id = Product });
                    return 0;
                }
                if (action == "--launch") { ownApp.Launch(); Print(new { launched = true, product_id = Product }); return 0; }
                if (action == "--stop") { ownApp.TerminateRunningInstances(); Print(new { stopped = true, product_id = Product }); return 0; }
                if (action == "--pair")
                {
                    if (args.Length != 2) throw new ArgumentException("--pair requires a private phone-config.json path");
                    string configPath = Path.GetFullPath(args[1]);
                    if (new FileInfo(configPath).Length > 8192) throw new InvalidDataException("Pairing config is too large");
                    var config = new JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string, object>>(File.ReadAllText(configPath));
                    object rawAddress, rawToken;
                    Uri origin;
                    if (!config.TryGetValue("address", out rawAddress) || !(rawAddress is string) || !Uri.TryCreate((string)rawAddress, UriKind.Absolute, out origin) || origin.Scheme != "http" || origin.AbsolutePath != "/" || origin.UserInfo.Length != 0 || origin.Query.Length != 0 || origin.Fragment.Length != 0)
                        throw new InvalidDataException("Pairing config needs an HTTP bridge origin");
                    if (!config.TryGetValue("device_token", out rawToken) || !(rawToken is string) || ((string)rawToken).Length < 24)
                        throw new InvalidDataException("Pairing config needs a device token");
                    operation = "open Lumia Agent isolated storage";
                    var privateStore = ownApp.GetIsolatedStore();
                    string knownLog = FindStoredFile(privateStore, "startup.log");
                    if (knownLog == null) throw new InvalidOperationException("Launch Lumia Agent once before pairing so its storage root can be identified");
                    string remoteConfig = knownLog.Substring(0, knownLog.Length - "startup.log".Length) + "phone-config.json";
                    operation = "copy private pairing config to Lumia Agent";
                    privateStore.SendFile(configPath, remoteConfig, !privateStore.FileExists(remoteConfig));
                    Print(new { config_transferred = true, product_id = Product, next_step = "Launch a version with pairing import support" });
                    return 0;
                }
                if (args.Length != 2) throw new ArgumentException("--logs requires a local output path");
                string destination = Path.GetFullPath(args[1]);
                if (File.Exists(destination)) throw new IOException("Log output already exists; choose a new path");
                operation = "open Lumia Agent isolated storage";
                var store = ownApp.GetIsolatedStore();
                operation = "find startup.log";
                string source = FindStoredFile(store, "startup.log");
                if (source == null) { Print(new { log_found = false, running = Running(ownApp) }); return 0; }
                operation = "retrieve startup.log";
                store.ReceiveFile(source, destination, true);
                Print(new { log_found = true, path = destination });
                return 0;
            }
            if (args.Length != 2) throw new ArgumentException("--install requires the built LumiaAgent.xap path");
            string package = Path.GetFullPath(args[1]);
            if (!File.Exists(package)) throw new FileNotFoundException("XAP not found", package);
            using (var archive = ZipFile.OpenRead(package))
            {
                var manifest = archive.GetEntry("WMAppManifest.xml");
                if (manifest == null) throw new InvalidOperationException("XAP has no Windows Phone manifest");
                using (var input = manifest.Open())
                using (var reader = XmlReader.Create(input, new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null }))
                {
                    var app = XDocument.Load(reader).Descendants().Single(e => e.Name.LocalName == "App");
                    if (new Guid((string)app.Attribute("ProductID")) != Product)
                        throw new InvalidOperationException("This deployer only installs the Lumia Agent product ID");
                }
            }
            string icon = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "ApplicationIcon.png");
            IRemoteApplication application;
            if (installed)
            {
                application = device.GetApplication(Product);
                operation = "update Lumia Agent";
                application.UpdateApplication("NormalApp", icon, package);
            }
            else
                application = device.InstallApplication(Product, Product, "NormalApp", icon, package);
            operation = "launch Lumia Agent";
            application.Launch();
            Print(new { installed = true, updated = installed, launched = true, product_id = Product, package = package });
            return 0;
        }
        catch (Exception error)
        {
            Print(new { operation = operation, error = error.Message, type = error.GetType().FullName, hresult = "0x" + error.HResult.ToString("X8"), detail = error.InnerException == null ? null : error.InnerException.Message });
            return 1;
        }
        finally
        {
            if (device != null)
                try { device.Disconnect(); } catch { }
        }
    }
}
