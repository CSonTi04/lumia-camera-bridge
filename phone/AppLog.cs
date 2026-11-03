using System;
using System.IO;
using System.IO.IsolatedStorage;

namespace LumiaAgent
{
    // Only lifecycle markers and exception types: never URLs or credentials.
    internal static class AppLog
    {
        public static void Exception(string marker, Exception error)
        {
            for (int depth = 0; error != null && depth < 8; depth++, error = error.InnerException)
            {
                Write(marker + " " + error.GetType().FullName);
                Write(error.StackTrace ?? "No stack trace");
            }
        }

        public static void Write(string marker)
        {
            try
            {
                using (var store = IsolatedStorageFile.GetUserStoreForApplication())
                {
                    if (store.FileExists("startup.log") && store.GetFileNames("startup.log").Length > 0)
                    {
                        using (var previous = store.OpenFile("startup.log", FileMode.Open, FileAccess.Read))
                            if (previous.Length > 65536) { previous.Close(); store.DeleteFile("startup.log"); }
                    }
                    using (var file = store.OpenFile("startup.log", FileMode.Append, FileAccess.Write))
                    using (var writer = new StreamWriter(file))
                        writer.WriteLine(DateTime.UtcNow.ToString("o") + " " + marker);
                }
            }
            catch { } // Diagnostics must never prevent application startup.
        }
    }
}
