namespace LumiaAgent
{
    internal sealed class FocusResult
    {
        public string Status;
        public int Attempts;
        public string Range;
        public string SupportedRanges;
    }

    internal sealed class CameraImage
    {
        public byte[] Jpeg;
        public FocusResult Focus;
        public string AppliedControlsJson;
    }
}
