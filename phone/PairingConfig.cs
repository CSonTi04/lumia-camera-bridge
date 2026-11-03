using System;
using System.IO;
using System.IO.IsolatedStorage;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;

namespace LumiaAgent
{
    [DataContract]
    public class PairingConfig
    {
        [DataMember] public string address { get; set; }
        [DataMember] public string device_token { get; set; }
        [DataMember] public bool connect_on_launch { get; set; }

        public static bool IsBridgeOrigin(string value, out Uri origin)
        {
            return Uri.TryCreate(value, UriKind.Absolute, out origin) && origin.Scheme == "http"
                && origin.AbsolutePath == "/" && String.IsNullOrEmpty(origin.UserInfo)
                && String.IsNullOrEmpty(origin.Query) && String.IsNullOrEmpty(origin.Fragment);
        }

        public static bool Import()
        {
            using (var store = IsolatedStorageFile.GetUserStoreForApplication())
            {
                if (!store.FileExists("phone-config.json")) return false;
                PairingConfig profile;
                using (var file = store.OpenFile("phone-config.json", FileMode.Open, FileAccess.Read))
                {
                    if (file.Length > 8192) throw new InvalidDataException("Pairing file too large");
                    profile = (PairingConfig)new DataContractJsonSerializer(typeof(PairingConfig)).ReadObject(file);
                }
                Uri origin;
                if (profile == null || !IsBridgeOrigin(profile.address, out origin)
                    || String.IsNullOrWhiteSpace(profile.device_token) || profile.device_token.Trim().Length < 24)
                    throw new InvalidDataException("Invalid pairing profile");
                var settings = IsolatedStorageSettings.ApplicationSettings;
                settings["address"] = origin.Scheme + "://" + origin.Authority;
                settings["device_token"] = profile.device_token.Trim();
                settings["connect_on_launch"] = profile.connect_on_launch;
                settings.Save();
                store.DeleteFile("phone-config.json");
                AppLog.Write("Private pairing imported");
                return true;
            }
        }
    }
}
