using System;
using System.Windows;
using Microsoft.Phone.Controls;
using Microsoft.Phone.Shell;

namespace LumiaAgent
{
    public class App : Application
    {
        public PhoneApplicationFrame RootFrame { get; private set; }

        public App()
        {
            AppLog.Write("App constructor 0.1.6");
            UnhandledException += (s, e) => {
                AppLog.Exception("Unhandled", e.ExceptionObject);
                MessageBox.Show("Lumia Agent error: " + e.ExceptionObject.GetType().Name);
            };
            var service = new PhoneApplicationService();
            service.Launching += (s, e) => AppLog.Write("Launching");
            service.Activated += (s, e) => AppLog.Write("Activated");
            service.Deactivated += (s, e) => AppLog.Write("Deactivated");
            service.Closing += (s, e) => AppLog.Write("Closing");
            ApplicationLifetimeObjects.Add(service);
            RootFrame = new PhoneApplicationFrame();
            RootFrame.Navigating += (s, e) => AppLog.Write("Navigating");
            RootFrame.Navigated += (s, e) => {
                AppLog.Write("Navigated");
                if (RootVisual != RootFrame) RootVisual = RootFrame;
            };
            RootFrame.NavigationFailed += (s, e) => {
                AppLog.Exception("Navigation failed", e.Exception);
                MessageBox.Show("Lumia Agent navigation failed: " + e.Exception.GetType().Name);
            };
            AppLog.Write("App initialized");
        }
    }
}
