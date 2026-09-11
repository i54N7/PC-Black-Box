using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using LibreHardwareMonitor.Hardware;

public sealed class UpdateVisitor : IVisitor
{
    public void VisitComputer(IComputer computer) => computer.Traverse(this);

    public void VisitHardware(IHardware hardware)
    {
        hardware.Update();
        foreach (IHardware subHardware in hardware.SubHardware)
            subHardware.Accept(this);
    }

    public void VisitSensor(ISensor sensor) { }
    public void VisitParameter(IParameter parameter) { }
}

public sealed class SensorSnapshot
{
    public long timestamp { get; set; }
    public double? cpu_temp { get; set; }
    public string? cpu_temp_name { get; set; }
    public string? gpu_name { get; set; }
    public double? gpu_usage { get; set; }
    public string? gpu_usage_name { get; set; }
    public double? gpu_temp { get; set; }
    public string? gpu_temp_name { get; set; }
}

internal static class Program
{
    private static IEnumerable<IHardware> Walk(IHardware hardware)
    {
        yield return hardware;
        foreach (IHardware sub in hardware.SubHardware)
        {
            foreach (IHardware child in Walk(sub))
                yield return child;
        }
    }

    private static int CpuTempScore(ISensor sensor)
    {
        string n = sensor.Name.ToLowerInvariant();
        int score = 0;
        if (n.Contains("tctl") || n.Contains("tdie")) score += 300;
        if (n.Contains("package")) score += 200;
        if (n.Contains("core average")) score += 100;
        if (n.Contains("core")) score += 50;
        return score;
    }

    private static int GpuLoadScore(ISensor sensor)
    {
        string n = sensor.Name.ToLowerInvariant();
        int score = 0;
        if (n.Contains("gpu core")) score += 300;
        if (n == "core" || n.Contains("core")) score += 250;
        if (n.Contains("d3d")) score += 150;
        if (n.Contains("total")) score += 100;
        return score;
    }

    private static int GpuTempScore(ISensor sensor)
    {
        string n = sensor.Name.ToLowerInvariant();
        int score = 0;
        if (n.Contains("gpu core")) score += 300;
        if (n.Contains("core")) score += 250;
        if (n.Contains("hot spot") || n.Contains("hotspot")) score += 200;
        if (n.Contains("gpu")) score += 100;
        return score;
    }

    private static bool IsGpuHardware(IHardware hw)
    {
        string t = hw.HardwareType.ToString();
        return t.StartsWith("Gpu", StringComparison.OrdinalIgnoreCase);
    }

    public static int Main(string[] args)
    {
        string outputPath = args.Length > 0
            ? Path.GetFullPath(args[0])
            : Path.Combine(AppContext.BaseDirectory, "hardware_sensors.json");

        var computer = new Computer
        {
            IsCpuEnabled = true,
            IsGpuEnabled = true,
            IsMemoryEnabled = false,
            IsMotherboardEnabled = true,
            IsControllerEnabled = true,
            IsStorageEnabled = false,
            IsNetworkEnabled = false
        };

        try
        {
            computer.Open();
            var visitor = new UpdateVisitor();

            // Warm-up passes for AMD sensors.
            for (int i = 0; i < 3; i++)
            {
                computer.Accept(visitor);
                Thread.Sleep(250);
            }

            while (true)
            {
                computer.Accept(visitor);

                ISensor? bestCpuTemp = null;
                int bestCpuScore = int.MinValue;

                IHardware? bestGpuHardware = null;
                ISensor? bestGpuLoad = null;
                int bestGpuLoadScore = int.MinValue;
                ISensor? bestGpuTemp = null;
                int bestGpuTempScore = int.MinValue;

                foreach (IHardware root in computer.Hardware)
                {
                    foreach (IHardware hw in Walk(root))
                    {
                        bool isGpu = IsGpuHardware(hw);

                        foreach (ISensor sensor in hw.Sensors)
                        {
                            if (!sensor.Value.HasValue)
                                continue;

                            double value = sensor.Value.Value;

                            // CPU temperature: only sensors on CPU hardware.
                            if (hw.HardwareType == HardwareType.Cpu &&
                                sensor.SensorType == SensorType.Temperature &&
                                value >= 5.0 && value <= 130.0)
                            {
                                int score = CpuTempScore(sensor);
                                if (score > bestCpuScore)
                                {
                                    bestCpuScore = score;
                                    bestCpuTemp = sensor;
                                }
                            }

                            if (!isGpu)
                                continue;

                            if (bestGpuHardware == null)
                                bestGpuHardware = hw;

                            if (sensor.SensorType == SensorType.Load &&
                                value >= 0.0 && value <= 100.0)
                            {
                                int score = GpuLoadScore(sensor);
                                if (score > bestGpuLoadScore)
                                {
                                    bestGpuLoadScore = score;
                                    bestGpuLoad = sensor;
                                    bestGpuHardware = hw;
                                }
                            }

                            if (sensor.SensorType == SensorType.Temperature &&
                                value >= 5.0 && value <= 130.0)
                            {
                                int score = GpuTempScore(sensor);
                                if (score > bestGpuTempScore)
                                {
                                    bestGpuTempScore = score;
                                    bestGpuTemp = sensor;
                                    bestGpuHardware = hw;
                                }
                            }
                        }
                    }
                }

                var snapshot = new SensorSnapshot
                {
                    timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
                    cpu_temp = bestCpuTemp?.Value,
                    cpu_temp_name = bestCpuTemp?.Name,
                    gpu_name = bestGpuHardware?.Name,
                    gpu_usage = bestGpuLoad?.Value,
                    gpu_usage_name = bestGpuLoad?.Name,
                    gpu_temp = bestGpuTemp?.Value,
                    gpu_temp_name = bestGpuTemp?.Name
                };

                string json = JsonSerializer.Serialize(snapshot);
                string tmpPath = outputPath + ".tmp";

                Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
                File.WriteAllText(tmpPath, json);
                File.Move(tmpPath, outputPath, true);

                Thread.Sleep(1000);
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
        finally
        {
            computer.Close();
        }
    }
}
