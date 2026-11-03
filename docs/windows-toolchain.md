# Windows build and USB deployment

The app is a Windows Phone 8.0 Silverlight XAP that runs on the tested WP8.1 handset. The build uses Windows' .NET Framework C# 5 compiler, genuine Microsoft reference assemblies, raw XAML stream resources, and ZIP packaging. It does not require a Visual Studio IDE or emulator.

## Build

Install Python 3.11+ and 7-Zip. In PowerShell at the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r bridge\requirements.txt
.\tools\setup-sdk.ps1
.\tools\build-phone.ps1
```

`setup-sdk.ps1` downloads the pinned Microsoft WP8 SDK ISO (1,721,982,976 bytes), verifies its SHA-256, validates Microsoft MSI signatures, and reads the MSI/CAB tables to extract references. It does not execute SDK installers. The download and extracted SDK stay in ignored local directories. Output: `build\LumiaAgent.xap`.

You can point the build at references you already obtained with `-SdkRoot PATH`. No SDK, firmware, driver or USB binary is distributed in this repository.

## USB deployment prerequisites

The phone must already permit sideloading, be in normal OS mode, and have its screen unlocked. Bootloader/root modification and factory-reset recovery are outside the build/deploy workflow. Preserve the existing Lumia Camera installation.

The tested workstation used Microsoft's standalone SDK connectivity components: IpOverUsb service, a WP8 physical-device CoreCon profile, the signed Sirep COM client, and managed device-connectivity assemblies. A full IDE was not needed.

**Fresh-workstation USB provisioning is not fully automated by this repository.** The optional setup helpers expect locally prepared Microsoft payloads. They do not fetch all USB artifacts or manufacture sideload authorization.

The prepared layout used by those helpers is:

```text
cache/usb-core/wpsdk_en.msi          # and its associated CAB payloads
cache/usb-profiles/WPSDK_en.msi      # shared SDK profile components
usb/profiles/ImageConfig.xsl        # genuine WP8 physical-device descriptor
usb/SirepClient.dll                 # signed Microsoft client
usb/sirep-registry.json             # registration records derived from the SDK MSI
usb/Microsoft.*.dll                 # required SDK managed connectivity assemblies
```

The WP8 device descriptor is in the SDK ISO's `packages/MobileTools/WPImages/cab3.cab` as `FL_Emulation_ImageConfig_xsl_x86_enu_V3`. Use artifacts from your lawful SDK copy. The profile/COM helpers verify expected names/signatures and refuse unrelated existing registrations. Transport installation and device-profile registration can require Windows administrator consent.

Once these components are configured:

```powershell
.\tools\build-deployer.ps1 -ConnectivityAssemblies PATH_TO_SDK_CONNECTIVITY_DLLS
.\tools\lumia.ps1 usb-status
.\tools\lumia.ps1 deploy
```

The bundled deployer **source** is restricted to Lumia Agent's product ID, `D66C350D-2C68-4C77-91F5-0871A6A44A83`. It updates this app in place and does not replace Nokia/Lumia Camera. Close Windows Phone Internals before SDK USB operations.

## Pairing and diagnostics

Manual pairing: enter `http://PI_LAN_IP:8765` and the Pi's device_token in the app.

Optional USB pairing: create a private `phone-config.json` at the checkout root using [the example](../examples/phone-config.example.json), with the real device credential. After owner authorization, `tools\lumia.ps1 pair` sends it to this app's isolated storage and updates/relaunches the built XAP. The app imports settings and deletes the incoming phone file. It can reconnect on launch.

`tools\lumia.ps1 usb-logs -OutFile NEW_LOG_PATH` retrieves only this app's startup markers. Read logs between camera tests: USB isolated-storage access may interrupt foreground operation. The SDK running-state query is unimplemented on the tested device; `usb-state` may report `running: null`.

Do not add credentials to source, compiler arguments or a XAP. Build and cache outputs are ignored by Git.
