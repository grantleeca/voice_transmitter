import sys
import wave
from contextlib import contextmanager

import pyaudio

DEFAULT_PORT = 1029

CHUNK = 1024  # 每个缓冲区的帧数
FORMAT = pyaudio.paInt16  # 采样位数
CHANNELS = 1  # 单声道
RATE = 44100  # 采样频率

# instantiate PyAudio (1)
pa = pyaudio.PyAudio()


@contextmanager
def open_audio_stream(*args, **kwargs):
    # open stream (2)
    stream = pa.open(*args, **kwargs)

    # play stream (3)
    yield stream

    # stop stream (4)
    stream.stop_stream()
    stream.close()


def record_audio(wave_out_path, record_second):
    """ 录音功能 """
    with open_audio_stream(format=FORMAT,
                           channels=CHANNELS,
                           rate=RATE,
                           input=True,
                           frames_per_buffer=CHUNK) as stream:
        wf = wave.open(wave_out_path, 'wb')  # 打开 wav 文件。
        wf.setnchannels(CHANNELS)  # 声道设置
        wf.setsampwidth(pyaudio.get_sample_size(FORMAT))  # 采样位数设置
        wf.setframerate(RATE)  # 采样频率设置

        for _ in range(0, int(RATE * record_second / CHUNK)):
            data = stream.read(CHUNK)
            wf.writeframes(data)  # 写入数据

        wf.close()


def play_audio(wave_file):
    with wave.open(wave_file, 'rb') as wf:
        with open_audio_stream(format=pyaudio.get_format_from_width(wf.getsampwidth()),
                               channels=wf.getnchannels(),
                               rate=wf.getframerate(),
                               output=True) as stream:
            # read data
            data = wf.readframes(CHUNK)

            while len(data):
                stream.write(data)
                data = wf.readframes(CHUNK)


def main(argv):
    for index in range(pa.get_host_api_count()):
        info = pa.get_host_api_info_by_index(index)
        print(info)

    device_count = pa.get_device_count()
    input_device = pa.get_default_input_device_info()
    output_device = pa.get_default_output_device_info()

    for index in range(device_count):
        info = pa.get_device_info_by_index(index)
        print(type(info), info)

    print('--------------------------------------------')
    print(f"Device count = {device_count}.\ninput: {input_device}. \noutput: {output_device}.")

    if len(argv) != 3:
        print(f'{argv[0]} -r/-p <record file name>')
        return

    if argv[1] == '-r':
        record_audio(argv[2], 3)
    elif argv[1] == '-p':
        play_audio(argv[2])
    else:
        print(f"Invalid command: {argv}")


if __name__ == '__main__':
    main(sys.argv)

    # close PyAudio (5)
    pa.terminate()
