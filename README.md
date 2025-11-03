# OvenMediaEngine Stress Tester

A tool designed to test OvenMediaEngine queue congestion by progressively starting FFmpeg streams at configurable intervals until receiving an INTERNAL_QUEUE_CONGESTION alert.

## Overview

This stress tester automatically:
- Starts an HTTP callback server to receive alerts from OvenMediaEngine.
- Progressively launches FFmpeg processes that stream to OvenMediaEngine.
- Monitors for the specific INTERNAL_QUEUE_CONGESTION alert.
- Reports test results, including the total number of streams and test duration, then stops all running processes.

## Prerequisites

### OvenMediaEngine
- OvenMediaEngine must be pre-configured to send alerts to the tester's host. [See example](#alert-configuration).
- OvenMediaEngine needs a pre-configured encoding profile in the target Application to test. [See example](#application-configuration).
- OvenMediaEngine must be able to access the host running tester app to send alerts.

### Tester App
- **Python 3.6 or higher** is required.
  - Please check the Python version by running either `python -V` or `python3 -V`.
- **FFmpeg** must be installed and executable.
  - Please check the FFmpeg installed by running either `ffmpeg -version` or `path/to/ffmpeg/ffmpeg -version`.
- A **Video file** to stream to OvenMediaEngine must be prepared.
  - We provide a sample video for the stress tester: `sample-video.mp4` (1080p, 30 fps, 5 Mbps).

## Project Structure

```
OMEStressTester/
├── OMEStressTester.py      # Main stress tester script
├── config.ini              # Configuration file for test parameters
├── sample-video.mp4        # Sample video file for streaming
├── ome-stress-tester.log   # Log file (generated during execution)
```

## Stress Tester Configuration

Edit the `config.ini` file to customize the test parameters:

```ini
[Server]
# Port for receiving OvenMediaEngine alert callbacks
# The endpoint of the alert callback server is fixed as http://your_test_app_host:alert_callback_server_port/callback
alert_callback_server_port = 8080

[Stream]
# Interval (in seconds) between starting each FFmpeg stream
ffmpeg_execution_interval = 10

# FFmpeg command template for RTMP streaming to OvenMediaEngine.
# Use ${seq} as a placeholder for stream sequence number.
# The tester will execute the command by incrementing ${seq} from 0 by 1 each time.
# Make sure to verify the OvenMediaEngine address (host, port, app name).

# Example for RTMP:
ffmpeg_command = ffmpeg -re -stream_loop -1 -i sample-video.mp4 -c copy -f flv rtmp://localhost:1935/app/stream_${seq}

# Example for SRT:
# ffmpeg_command = ffmpeg -re -stream_loop -1 -i sample-video.mp4 -c copy -f mpegts srt://localhost:9999?streamid=default/app/stream_${seq}
```

## OvenMediaEngine Configuration

### Alert configuration

Configure OvenMediaEngine to send alerts to the tester. Add the `InternalQueueCongestion` rule to your Alert configuration:

```xml
<Alert>
    <Url>http://your_test_app_host:8080/callback</Url>
    <SecretKey>1234</SecretKey>
    <Timeout>3000</Timeout>
    <Rules>
        <InternalQueueCongestion />
    </Rules>
</Alert>
```


### Application configuration

Pre-configure the output profile to test.

```xml
<Application>
  <Name>perf</Name>
  <Type>live</Type>
  <OutputProfiles>
    <!-- Common setting for decoders. Decodes is optional. -->
    <Decodes>
      <!-- Number of threads for the decoder. -->
      <ThreadCount>2</ThreadCount>
      <!-- 
        By default, OME decodes all video frames. 
        With OnlyKeyframes, only keyframes are decoded, massively improving performance.
        Thumbnails are generated only on keyframes, they may not generate at your requested fps!
        -->
      <OnlyKeyframes>false</OnlyKeyframes>
    </Decodes>

    <!-- Enable this configuration if you want to hardware acceleration using GPU -->
    <HWAccels>
      <Decoder>
        <Enable>false</Enable>
        <!-- 
          Setting for Hardware Modules.
            - xma :Xilinx Media Accelerator
            - qsv :Intel Quick Sync Video
            - nv : Nvidia Video Codec SDK
            - nilogan: Netint VPU

          You can use multiple modules by separating them with commas.
          For example, if you want to use xma and nv, you can set it as follows.

          <Modules>[ModuleName]:[DeviceId],[ModuleName]:[DeviceId],...</Modules>
          <Modules>xma:0,nv:0</Modules>
        -->
        <!-- <Modules>nv</Modules> -->
      </Decoder>
      <Encoder>
        <Enable>false</Enable>
        <!-- <Modules>nv</Modules> -->
      </Encoder>
    </HWAccels>

    <OutputProfile>
      <Name>default</Name>
      <OutputStreamName>${OriginStreamName}</OutputStreamName>
      <Encodes>
        <Video>
          <Name>video_1280</Name>
          <Codec>h264</Codec>
          <Bitrate>5024000</Bitrate>
          <Width>1920</Width>
          <Height>1080</Height>
          <Framerate>30</Framerate>
          <KeyFrameInterval>30</KeyFrameInterval>
          <BFrames>0</BFrames>
          <Preset>faster</Preset>
        </Video>
        <Audio>
          <Name>bypass_audio</Name>
          <Bypass>true</Bypass>
        </Audio>
      </Encodes>
    </OutputProfile>
  </OutputProfiles>
  <Providers>
    <OVT />
    <RTMP />
    <SRT />
  </Providers>
  <Publishers>
    <AppWorkerCount>1</AppWorkerCount>
    <StreamWorkerCount>8</StreamWorkerCount>
    <OVT />
    <LLHLS>
      <ChunkDuration>1</ChunkDuration>
      <PartHoldBack>3</PartHoldBack>
      <SegmentDuration>6</SegmentDuration>
      <SegmentCount>10</SegmentCount>
      <CrossDomains>
        <Url>*</Url>
      </CrossDomains>
      <CreateDefaultPlaylist>true</CreateDefaultPlaylist>
    </LLHLS>
    <HLS>
      <SegmentCount>4</SegmentCount>
      <SegmentDuration>4</SegmentDuration>
      <CrossDomains>
        <Url>*</Url>
      </CrossDomains>
      <CreateDefaultPlaylist>true</CreateDefaultPlaylist>
    </HLS>
  </Publishers>
</Application>
```

## Usage

### Running the Tester

```bash
python OMEStressTester.py
```

or 

```bash
python3 OMEStressTester.py
```

### Expected Output

The tester will display:

**At Startup:**
```
============================================================
Stress Tester for OvenMediaEngine v1.0.0
============================================================
Configuration:
  - Log File: ome-stress-tester.log
  - Alert Callback Server Port: 8080
  - FFmpeg Execution Interval: 10 seconds
  - FFmpeg Command: ffmpeg -re -stream_loop -1 -i sample-video.mp4 -c copy -f flv rtmp://localhost:1935/perf/stream_${seq}
============================================================
Alert callback server running on port 8080
Execute FFmpeg. seq: 0, cmd: ffmpeg -re -stream_loop -1 -i sample-video.mp4 -c copy -f flv rtmp://localhost:1935/perf/stream_0
Execute FFmpeg. seq: 1, cmd: ffmpeg -re -stream_loop -1 -i sample-video.mp4 -c copy -f flv rtmp://localhost:1935/perf/stream_1
...
```

**When Alert is Received:**
```
INTERNAL_QUEUE_CONGESTION alert received.
Stopping all FFMPEG processes...
============================================================
Test Results:
  - Alert Type: INTERNAL_QUEUE_CONGESTION
  - Total Streams Started: 11
  - Test Duration: 115.68 seconds
============================================================
```

## Log Files

Test logs are saved to `ome-stress-tester.log` in the project directory. The log includes:
- Configuration at startup
- Each FFmpeg stream start with full command
- Alert callbacks received
- Test results summary
- Any errors encountered