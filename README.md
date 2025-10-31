# Stress Tester for OvenMediaEngine

A tool to test OvenMediaEngine stress by progressively starting FFmpeg streams at configurable intervals until receiving an INTERNAL_QUEUE_CONGESTION alert.

## Overview

This tester automatically:
1. Starts an HTTP callback server to receive alerts from OvenMediaEngine
2. Progressively launches FFmpeg processes that stream to OvenMediaEngine
3. Monitors for INTERNAL_QUEUE_CONGESTION alerts
4. Reports test results including total streams, duration, and stops all processes

## Prerequisites

### OvenMediaEngine
- OvenMediaEngine is pre-configured to send alerts
- OvenMediaEngine has pre-configured encoding profile to test
- OvenMediaEngine must be able to access the host running this tester

### Tester App
- Python 3.6 or higher
- FFmpeg installed

## Tester Configuration

Edit `config.ini` to customize the test parameters:

```ini
[Server]
# Port for receiving OvenMediaEngine alert callbacks
alert_callback_server_port = 8080

[Stream]
# Interval (in seconds) between starting each FFmpeg stream
ffmpeg_execution_interval = 10

# FFmpeg command template for RTMP streaming
# ${seq} will be replaced with sequential numbers (0, 1, 2, ...)
# Update the RTMP URL to match your OvenMediaEngine configuration
ffmpeg_command = ffmpeg -re -stream_loop -1 -i sample-video.mp4 -c copy -f flv rtmp://localhost:1935/perf/stream_${seq}
```

## OvenMediaEngine Configuration

### Alert

Configure OvenMediaEngine to send alerts to 솓 tester. Add the `InternalQueueCongestion` rule to your OvenMediaEngine alert configuration

```xml
<Alert>
    <Url>http://your_host:8080/callback</Url>
    <SecretKey>1234</SecretKey>
    <Timeout>3000</Timeout>
    <Rules>
        <InternalQueueCongestion />
    </Rules>
</Alert>
```


### App

Pre-configure the output profile in the following format:

```xml
<Application>
  <Name>perf</Name>
  <!-- Application type (live/vod) -->
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
      <!-- <PartHoldBack> SHOULD be at least three times the <ChunkDuration> -->
      <PartHoldBack>3</PartHoldBack>
      <SegmentDuration>6</SegmentDuration>
      <SegmentCount>10</SegmentCount>
      <CrossDomains>
        <Url>*</Url>
      </CrossDomains>
      <CreateDefaultPlaylist>true</CreateDefaultPlaylist>      <!-- llhls.m3u8 -->
    </LLHLS>
    <HLS>
      <SegmentCount>4</SegmentCount>
      <SegmentDuration>4</SegmentDuration>
      <CrossDomains>
        <Url>*</Url>
      </CrossDomains>
      <CreateDefaultPlaylist>true</CreateDefaultPlaylist>      <!-- ts:playlist.m3u8 -->
    </HLS>
  </Publishers>
</Application>
```

## Usage

### Running the Tester

```shell
python OMEStressTester.py
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
  - Total Streams Started: 15
  - Active Streams at Alert: 15
  - Test Duration: 150.45 seconds
  - FFmpeg Execution Interval: 10 seconds
============================================================
Program terminating...
```

## Log Files

Test logs are saved to `stress-tester.log` in the project directory. The log includes:
- Configuration at startup
- Each FFmpeg stream start with full command
- Alert callbacks received
- Test results summary
- Any errors encountered