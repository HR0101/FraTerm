"""再生制御と表示補助に関するテスト."""

from __future__ import annotations

import io

import pytest

from fraterm import audio, config
from fraterm.errors import AudioError, PlaybackError, VideoFileError
from fraterm.player import PlaybackOptions, Player, formatTime
from fraterm.registry import VideoEntry
from fraterm.textwidth import displayWidth, padToWidth, truncateToWidth


@pytest.mark.parametrize(
  "seconds, expected",
  [(0, "00:00"), (5, "00:05"), (65, "01:05"), (3661, "1:01:01"), (-1, "--:--")],
)
def test_formatTime(seconds, expected):
  """秒数が時刻表記へ変換されることを確認する."""
  assert formatTime(seconds) == expected


@pytest.mark.parametrize(
  "rawText, expected",
  [
    ("普通のタイトル", "普通のタイトル"),
    ("危険\x1b[2Jな\x1b[31mタイトル", "危険な タイトル".replace(" ", "")),
    ("改行\nと\tタブ", "改行とタブ"),
    ("制御\x07文字", "制御文字"),
  ],
)
def test_sanitizeTextRemovesControlCharacters(rawText, expected):
  """外部由来の文字列から端末制御文字を取り除くことを確認する."""
  from fraterm.textwidth import sanitizeText

  assert sanitizeText(rawText) == expected


def test_statusLineDoesNotLeakControlCharacters(dummyVideo):
  """タイトルに仕込まれたANSIコードがステータス行へ出ないことを確認する."""
  options = PlaybackOptions(title="悪意\x1b[2J\x1b[31mあるタイトル")
  player = Player(dummyVideo, options, stream=io.StringIO())
  player._startClock()

  statusText = player._statusText(10, 200)
  # 自前で付けている装飾以外のエスケープが含まれていないことを確かめる
  body = statusText.split("H", 1)[1]
  assert "\x1b[2J" not in body
  assert "\x1b[31m" not in body


def test_displayWidthCountsWideCharacters():
  """全角文字が2文字分として数えられることを確認する."""
  assert displayWidth("abc") == 3
  assert displayWidth("再生中") == 6


def test_truncateToWidthKeepsLimit():
  """表示幅の上限を超えないように切り詰められることを確認する."""
  assert displayWidth(truncateToWidth("再生中です", 5)) <= 5
  assert truncateToWidth("abcdef", 3) == "abc"
  assert truncateToWidth("abc", 0) == ""


def test_padToWidthFillsWithSpaces():
  """表示幅がそろうように空白が追加されることを確認する."""
  assert padToWidth("abc", 5) == "abc  "
  assert displayWidth(padToWidth("音声", 6)) == 6


def test_playbackOptionsFromEntry(dummyVideo):
  """登録情報から再生設定が作られることを確認する."""
  entry = VideoEntry(
    name="sample",
    path=str(dummyVideo),
    mode="color",
    audio=True,
    width=120,
    fps=24.0,
    charset="simple",
  )
  options = PlaybackOptions.fromEntry(entry)

  assert options.mode == "color"
  assert options.audio is True
  assert options.width == 120
  assert options.fps == 24.0
  assert options.charset == "simple"
  assert options.title == "sample"


@pytest.mark.parametrize("key", ["q", "Q", "\x1b", "\x03"])
def test_quitKeysStopPlayback(dummyVideo, key):
  """q・Esc・Ctrl+C が再生終了を要求することを確認する."""
  player = Player(dummyVideo)
  assert player._handleKey(key) is False


def test_otherKeysContinuePlayback(dummyVideo):
  """終了以外のキーでは再生が続くことを確認する."""
  player = Player(dummyVideo)
  assert player._handleKey("x") is True


def test_escapeCancelsSaveInsteadOfQuitting(dummyVideo):
  """保存名の入力中は，Escが終了ではなく取り消しになることを確認する."""
  savedNames: list[str] = []
  options = PlaybackOptions(onSave=lambda name: savedNames.append(name) or "保存しました．")
  player = Player(dummyVideo, options, stream=io.StringIO())
  player._startClock()
  player._lastSize = (40, 10, 80, 24)
  player._keyReader = ScriptedKeyReader(["a", "\x1b", "x"])

  # s を押しても再生は終了せず，Escで入力だけが取り消される
  assert player._handleKey("s") is True
  assert savedNames == []


def test_pauseFreezesMediaTime(dummyVideo):
  """一時停止中に再生位置が進まないことを確認する."""
  player = Player(dummyVideo)
  player._startClock()
  player._togglePause()

  firstPosition = player._mediaTime()
  secondPosition = player._mediaTime()
  assert firstPosition == secondPosition

  player._togglePause()
  assert player._paused is False


def test_speedChangeIsClamped(dummyVideo):
  """再生速度が上下限の範囲に収まることを確認する."""
  player = Player(dummyVideo)
  player._startClock()

  for _ in range(50):
    player._changeSpeed(config.SPEED_STEP)
  assert player._speed == config.MAX_SPEED

  for _ in range(50):
    player._changeSpeed(-config.SPEED_STEP)
  assert player._speed == config.MIN_SPEED


def test_seekByClampsPositionAndUpdatesFrameIndex(dummyVideo):
  """シークが秒数・フレーム番号・音声同期の基準を更新することを確認する."""
  player = Player(dummyVideo, PlaybackOptions(), stream=io.StringIO())
  player._videoFps = 10.0
  player._duration = 60.0
  player._mediaTime = lambda: 20.0
  player._startClock = lambda: None
  player._syncAudio = lambda: None

  player._seekBy(config.SEEK_STEP_SECONDS)

  assert player._mediaBase == 30.0
  assert player._nextFrameIndex == 300


def test_seekKeysUseTenSecondStep(dummyVideo):
  """左右矢印とh/lがシーク操作へ割り当てられていることを確認する."""
  from fraterm.keyboard import KEY_LEFT, KEY_RIGHT

  player = Player(dummyVideo, stream=io.StringIO())
  moved: list[float] = []
  player._seekBy = lambda seconds: moved.append(seconds)

  assert player._handleKey(KEY_LEFT) is True
  assert player._handleKey(KEY_RIGHT) is True
  assert player._handleKey("h") is True
  assert player._handleKey("l") is True
  assert moved == [
    -config.SEEK_STEP_SECONDS,
    config.SEEK_STEP_SECONDS,
    -config.SEEK_STEP_SECONDS,
    config.SEEK_STEP_SECONDS,
  ]


class FakeCapture:
  """OpenCV の VideoCapture を模したテスト用のクラス."""

  def __init__(self, opened: bool) -> None:
    self._opened = opened
    self.released = False

  def isOpened(self) -> bool:
    return self._opened

  def release(self) -> None:
    self.released = True


class FakeCv2:
  """指定回数だけ読み込みに失敗する OpenCV の代役."""

  CAP_ANY = 0
  CAP_FFMPEG = 1900

  def __init__(self, failures: int = 0) -> None:
    self.failures = failures
    self.calls: list[tuple[str, int]] = []
    self.captures: list[FakeCapture] = []

  def VideoCapture(self, path, backend):  # noqa: N802 OpenCV の名前に合わせる
    self.calls.append((path, backend))
    capture = FakeCapture(len(self.calls) > self.failures)
    self.captures.append(capture)
    return capture


def test_urlUsesFfmpegBackend(monkeypatch):
  """URLではFFmpegを明示して開くことを確認する."""
  monkeypatch.setattr(config, "REMOTE_OPEN_RETRY_DELAY", 0)
  player = Player("https://example.invalid/video.mp4", stream=io.StringIO())
  fakeCv2 = FakeCv2()

  player._openCapture(fakeCv2)
  assert fakeCv2.calls == [("https://example.invalid/video.mp4", FakeCv2.CAP_FFMPEG)]


def test_localFileUsesDefaultBackend(dummyVideo):
  """ローカルファイルでは従来どおり自動選択で開くことを確認する."""
  player = Player(dummyVideo, stream=io.StringIO())
  fakeCv2 = FakeCv2()

  player._openCapture(fakeCv2)
  assert fakeCv2.calls[0][1] == FakeCv2.CAP_ANY
  assert len(fakeCv2.calls) == 1  # ファイルは再試行しない


def test_urlIsRetriedOnTemporaryFailure(monkeypatch, capsys):
  """URLの一時的な失敗を再試行で乗り越えられることを確認する."""
  monkeypatch.setattr(config, "REMOTE_OPEN_RETRY_DELAY", 0)
  player = Player("https://example.invalid/video.mp4", stream=io.StringIO())
  fakeCv2 = FakeCv2(failures=1)  # 1回目だけ失敗する

  capture = player._openCapture(fakeCv2)
  assert capture.isOpened() is True
  assert len(fakeCv2.calls) == 2
  assert "再試行" in capsys.readouterr().err


def test_urlFailureSuggestsCacheOption(monkeypatch):
  """URLを開けない場合に --cache を案内することを確認する."""
  monkeypatch.setattr(config, "REMOTE_OPEN_RETRY_DELAY", 0)
  player = Player("https://example.invalid/video.mp4", stream=io.StringIO())
  fakeCv2 = FakeCv2(failures=99)

  with pytest.raises(PlaybackError) as errorInfo:
    player._openCapture(fakeCv2)

  assert "--cache" in (errorInfo.value.hint or "")
  assert len(fakeCv2.calls) == config.REMOTE_OPEN_ATTEMPTS
  # 開けなかった分は後始末されている
  assert all(capture.released for capture in fakeCv2.captures)


def test_localFailureKeepsFormatHint(dummyVideo):
  """ローカルファイルの失敗では，従来どおり形式の案内を出すことを確認する."""
  player = Player(dummyVideo, stream=io.StringIO())
  fakeCv2 = FakeCv2(failures=99)

  with pytest.raises(PlaybackError) as errorInfo:
    player._openCapture(fakeCv2)

  assert "--cache" not in (errorInfo.value.hint or "")
  assert "対応していない形式" in (errorInfo.value.hint or "")


def test_longUrlIsShortenedInErrorMessage(monkeypatch):
  """長いURLがエラー表示で切り詰められることを確認する."""
  monkeypatch.setattr(config, "REMOTE_OPEN_RETRY_DELAY", 0)
  longUrl = "https://example.invalid/videoplayback?" + "a=1&" * 200
  player = Player(longUrl, stream=io.StringIO())

  with pytest.raises(PlaybackError) as errorInfo:
    player._openCapture(FakeCv2(failures=99))

  assert len(errorInfo.value.message) < 200
  assert len(longUrl) > 400


def test_titleIsUsedInErrorMessageWhenAvailable(monkeypatch):
  """タイトルが分かっている場合は，URLではなくタイトルで知らせることを確認する."""
  monkeypatch.setattr(config, "REMOTE_OPEN_RETRY_DELAY", 0)
  options = PlaybackOptions(title="テスト動画")
  player = Player("https://example.invalid/a?b=1", options, stream=io.StringIO())

  with pytest.raises(PlaybackError) as errorInfo:
    player._openCapture(FakeCv2(failures=99))

  assert "テスト動画" in errorInfo.value.message
  assert "example.invalid" not in errorInfo.value.message


def test_missingVideoRaises(tmp_path):
  """存在しない動画を再生しようとした場合のエラーを確認する."""
  with pytest.raises(VideoFileError):
    Player(tmp_path / "none.mp4", stream=io.StringIO()).play()


def test_unreadableVideoRaises(dummyVideo):
  """読み込めない動画ファイルでエラーになることを確認する."""
  with pytest.raises(PlaybackError):
    Player(dummyVideo, stream=io.StringIO()).play()


def test_audioRequiresFfplay(dummyVideo, monkeypatch):
  """ffplay が無い状態で --audio を指定した場合のエラーを確認する."""
  monkeypatch.setattr(audio, "isAvailable", lambda: False)
  options = PlaybackOptions(audio=True)

  with pytest.raises(AudioError):
    Player(dummyVideo, options, stream=io.StringIO()).play()


@pytest.mark.parametrize("mode", config.AVAILABLE_MODES)
def test_playSampleVideoToStream(sampleVideo, mode):
  """実際の動画を最後まで再生し，出力と後始末を確認する."""
  stream = io.StringIO()
  options = PlaybackOptions(mode=mode, width=40, title="sample")

  Player(sampleVideo, options, stream=stream).play()
  output = stream.getvalue()

  assert output, "フレームが出力されていません"
  assert "\x1b[H" in output  # カーソル位置の指定が含まれる
  assert output.endswith("\x1b[0m\n")  # 文字色を戻して終了している


def test_playRespectsFpsLimit(sampleVideo):
  """FPS上限を指定すると描画回数が減ることを確認する."""
  baseStream = io.StringIO()
  Player(sampleVideo, PlaybackOptions(width=40), stream=baseStream).play()

  limitedStream = io.StringIO()
  Player(sampleVideo, PlaybackOptions(width=40, fps=2), stream=limitedStream).play()

  baseFrames = baseStream.getvalue().count("\x1b[H")
  limitedFrames = limitedStream.getvalue().count("\x1b[H")
  assert limitedFrames < baseFrames


def test_preRenderGeneratesFramesBeforePlayback(sampleVideo):
  """事前生成を有効にしても全フレームが順番に描画されることを確認する."""
  stream = io.StringIO()
  options = PlaybackOptions(width=40, preRender=True, title="sample")

  Player(sampleVideo, options, stream=stream).play()

  assert stream.getvalue().count("\x1b[H") == 10
  assert stream.getvalue().endswith("\x1b[0m\n")


def test_renderedFrameIsCenteredInTerminal(dummyVideo):
  """映像が端末の上下左右の中央へ配置されることを確認する."""
  stream = io.StringIO()
  player = Player(dummyVideo, PlaybackOptions(showStatus=False), stream=stream)

  player._writeRenderedFrame("aa\nbb", 2, 2, 10, 8)

  output = stream.getvalue()
  assert "\x1b[4;1H" in output  # 上余白3行の4行目から描画
  assert "    aa\x1b[K\n    bb" in output  # 左余白4桁を各行へ適用


class FakeAudioPlayer:
  """ffplay を起動せず，呼び出し内容だけを記録するテスト用の音声プレイヤー."""

  def __init__(self) -> None:
    self.starts: list[dict] = []
    self.stopCount = 0
    self.readyPosition: float | None = None
    self.waitTimeouts: list[float] = []

  def start(self, position=0.0, speed=1.0, volume=config.DEFAULT_VOLUME) -> None:
    self.starts.append({"position": position, "speed": speed, "volume": volume})

  def stop(self) -> None:
    self.stopCount += 1

  def waitUntilReady(self, timeout=config.AUDIO_READY_TIMEOUT):
    self.waitTimeouts.append(timeout)
    return self.readyPosition


def makeAudioPlayer(dummyVideo, **optionValues):
  """音声を有効にしたプレイヤーと，差し替えた音声プレイヤーを返す."""
  options = PlaybackOptions(audio=True, **optionValues)
  player = Player(dummyVideo, options, stream=io.StringIO())
  fakeAudio = FakeAudioPlayer()
  player._audioPlayer = fakeAudio
  player._startClock()
  return player, fakeAudio


@pytest.mark.parametrize(
  "status, expected",
  [
    ("   0.55 M-A:  0.000", 0.55),
    ("\x1b[2K\r   12.345 M-A: -0.001", 12.345),
    ("    nan M-A:    nan", None),
    ("audio decoder is ready", None),
  ],
)
def test_audioPositionFromStatus(status, expected):
  """ffplayの進捗行から音声位置だけを安全に取り出す."""
  assert audio.audioPositionFromStatus(status) == expected


def test_audioStartsAtCurrentMediaPosition(dummyVideo):
  """音声を固定補正せず，現在の映像位置から開始することを確認する."""
  player, fakeAudio = makeAudioPlayer(dummyVideo)
  player._mediaTime = lambda: 0.0
  player._syncAudio()

  assert len(fakeAudio.starts) == 1
  assert fakeAudio.starts[0]["position"] == pytest.approx(0.0)


def test_audioOffsetShiftsStartPosition(dummyVideo):
  """--audio-offset の指定が開始位置へ反映されることを確認する."""
  player, fakeAudio = makeAudioPlayer(dummyVideo, audioOffset=1.5)
  player._mediaTime = lambda: 0.0
  player._syncAudio()

  assert fakeAudio.starts[0]["position"] == pytest.approx(1.5)


def test_audioReadyPositionRebasesVideoClock(dummyVideo):
  """ffplayから受け取った音声位置を基準に映像クロックを合わせる."""
  player, fakeAudio = makeAudioPlayer(dummyVideo, audioOffset=1.5)
  player._mediaTime = lambda: 10.0
  fakeAudio.readyPosition = 12.5

  player._syncAudio()

  assert player._mediaBase == pytest.approx(11.0)
  assert fakeAudio.waitTimeouts == [config.AUDIO_READY_TIMEOUT]


def test_volumeKeysChangeVolume(dummyVideo):
  """9と0のキーで音量が変わり，音声を鳴らし直すことを確認する."""
  player, fakeAudio = makeAudioPlayer(dummyVideo, volume=50)

  player._handleKey("0")
  assert player._volume == 50 + config.VOLUME_STEP
  assert fakeAudio.starts[-1]["volume"] == player._volume

  player._handleKey("9")
  assert player._volume == 50


def test_volumeIsClamped(dummyVideo):
  """音量が上下限を超えないことを確認する."""
  player, _ = makeAudioPlayer(dummyVideo, volume=config.MAX_VOLUME)
  player._handleKey("0")
  assert player._volume == config.MAX_VOLUME

  player, _ = makeAudioPlayer(dummyVideo, volume=config.MIN_VOLUME)
  player._handleKey("9")
  assert player._volume == config.MIN_VOLUME


def test_pauseStopsAudioAndResumeRestarts(dummyVideo):
  """一時停止で音声が止まり，再開で鳴り直すことを確認する."""
  player, fakeAudio = makeAudioPlayer(dummyVideo)

  player._handleKey(" ")
  assert player._paused is True
  assert fakeAudio.stopCount >= 1

  startsBeforeResume = len(fakeAudio.starts)
  player._handleKey(" ")
  assert player._paused is False
  assert len(fakeAudio.starts) == startsBeforeResume + 1


def test_muteStopsAudio(dummyVideo):
  """mキーで消音でき，もう一度押すと戻ることを確認する."""
  player, fakeAudio = makeAudioPlayer(dummyVideo)

  player._handleKey("m")
  assert player._muted is True
  assert fakeAudio.stopCount >= 1

  startsBeforeUnmute = len(fakeAudio.starts)
  player._handleKey("m")
  assert player._muted is False
  assert len(fakeAudio.starts) == startsBeforeUnmute + 1


def test_volumeKeysAreIgnoredWithoutAudio(dummyVideo):
  """音声を使わない再生では音量キーが何もしないことを確認する."""
  player = Player(dummyVideo, PlaybackOptions(), stream=io.StringIO())
  player._startClock()

  assert player._handleKey("0") is True
  assert player._volume == config.DEFAULT_VOLUME


@pytest.mark.parametrize(
  "rawInput, expected",
  [
    ("myclip", (["m", "y", "c", "l", "i", "p"], "")),  # 文字入力はすべて取り出す
    ("a", (["a"], "")),
    ("\x1b", ([], "\x1b")),  # Esc単独か続きがあるか未確定のため保留する
    ("\x1b[A", (["\x1b[A"], "")),  # 矢印キーは操作に使うため取り出す
    ("ab\x1b[Bcd", (["a", "b", "\x1b[B", "c", "d"], "")),
    ("\x1b[1;2A", ([], "")),  # 修飾キー付きなど，扱わないシーケンスは読み飛ばす
    ("\x1b[6~", ([], "")),  # PageDown なども読み飛ばす
    ("\x1b[", ([], "\x1b[")),  # 途中で切れたシーケンスは持ち越す
    ("a\x1b[", (["a"], "\x1b[")),
    ("\r", (["\r"], "")),
  ],
)
def test_keyTokenize(rawInput, expected):
  """まとめて届いた入力を1キーずつへ分解できることを確認する."""
  from fraterm.keyboard import KeyReader

  assert KeyReader._tokenize(rawInput) == expected


def test_splitEscapeSequenceIsRestored():
  """読み取りの境界で分断された矢印キーを取りこぼさないことを確認する."""
  from fraterm.keyboard import KEY_DOWN, KeyReader

  reader = KeyReader()
  rawInput = KEY_DOWN * 7
  collected: list[str] = []

  # 端末から8バイトずつ届いた状況を再現する
  for start in range(0, len(rawInput), 8):
    key = reader._takeFirst(rawInput[start : start + 8])
    while key is not None:
      collected.append(key)
      key = reader.readKey()

  assert collected == [KEY_DOWN] * 7


def test_loneEscapeIsReportedAfterTimeout(monkeypatch):
  """続きが来なかったEscキーが，少し待ってから確定することを確認する."""
  from fraterm.keyboard import ESC, KeyReader

  reader = KeyReader()
  assert reader._takeFirst(ESC) is None  # この時点では確定しない
  assert reader._flushPartialInput() is None  # 待ち時間が足りない

  reader._partialSince -= 1.0  # 十分な時間が過ぎた状況にする
  assert reader._flushPartialInput() == ESC


def test_arrowKeysAreNotTypedAsText(dummyVideo):
  """保存名の入力欄に矢印キーの文字列が入らないことを確認する."""
  from fraterm.keyboard import KEY_DOWN

  savedNames: list[str] = []
  options = PlaybackOptions(onSave=lambda name: savedNames.append(name) or "保存しました．")
  player = Player(dummyVideo, options, stream=io.StringIO())
  player._startClock()
  player._lastSize = (40, 10, 80, 24)
  player._keyReader = ScriptedKeyReader(["a", KEY_DOWN, "b", "\r", "x"])

  player._handleKey("s")
  assert savedNames == ["ab"]


def test_pendingKeysAreReturnedInOrder():
  """余った入力が次回以降の読み取りで順に返ることを確認する."""
  from fraterm.keyboard import KeyReader

  reader = KeyReader()
  assert reader._takeFirst("abc") == "a"
  assert reader.readKey() == "b"
  assert reader.readKey() == "c"
  assert reader.readKey() is None


def test_saveKeyPromptsAndCallsHandler(dummyVideo):
  """sキーで保存名を尋ね，入力した名前で保存処理を呼ぶことを確認する."""
  savedNames: list[str] = []

  options = PlaybackOptions(onSave=lambda name: savedNames.append(name) or "保存しました．")
  player = Player(dummyVideo, options, stream=io.StringIO())
  player._startClock()
  # 画面サイズを確定させ，入力欄を描けるようにする
  player._lastSize = (40, 10, 80, 24)
  player._keyReader = ScriptedKeyReader(list("myclip") + ["\r", "x"])

  player._handleKey("s")

  assert savedNames == ["myclip"]
  assert player._paused is False  # 保存後は再生状態へ戻る


def test_saveCanBeCancelledWithEscape(dummyVideo):
  """Escキーで保存を取り消せることを確認する."""
  savedNames: list[str] = []

  options = PlaybackOptions(onSave=lambda name: savedNames.append(name) or "保存しました．")
  player = Player(dummyVideo, options, stream=io.StringIO())
  player._startClock()
  player._lastSize = (40, 10, 80, 24)
  player._keyReader = ScriptedKeyReader(["a", "b", "\x1b"])

  player._handleKey("s")
  assert savedNames == []


def test_saveKeyIsIgnoredWithoutHandler(dummyVideo):
  """保存処理が設定されていない場合はsキーが何もしないことを確認する."""
  player = Player(dummyVideo, PlaybackOptions(), stream=io.StringIO())
  player._startClock()
  player._keyReader = ScriptedKeyReader(["\r"])

  assert player._handleKey("s") is True
  assert player._paused is False


def test_saveFailureIsShownWithoutStoppingPlayback(dummyVideo):
  """保存に失敗しても再生が続くことを確認する."""
  def failingSave(name: str) -> str:
    raise RuntimeError("書き込みできません")

  player = Player(dummyVideo, PlaybackOptions(onSave=failingSave), stream=io.StringIO())
  player._startClock()
  player._lastSize = (40, 10, 80, 24)
  player._keyReader = ScriptedKeyReader(["x", "\r", "y"])

  assert player._handleKey("s") is True
  assert player._paused is False


def test_signalHandlersAreInstalledAndRestored(dummyVideo):
  """終了シグナルのハンドラを設定し，後で元へ戻すことを確認する."""
  import signal

  player = Player(dummyVideo, stream=io.StringIO())
  original = signal.getsignal(signal.SIGTERM)

  player._installSignalHandlers()
  assert signal.getsignal(signal.SIGTERM) is player._onTerminationSignal

  player._restoreSignalHandlers()
  assert signal.getsignal(signal.SIGTERM) is original


def test_terminationSignalRaisesInterrupt():
  """終了シグナルが割り込みとして送出されることを確認する."""
  with pytest.raises(KeyboardInterrupt):
    Player._onTerminationSignal(15, None)


class ScriptedKeyReader:
  """待機のたびに，あらかじめ決めたキーを返すテスト用の入力クラス."""

  def __init__(self, keys) -> None:
    self.keys = list(keys)
    self.pressedKeys: list[str] = []

  def __enter__(self) -> "ScriptedKeyReader":
    return self

  def __exit__(self, *exceptionInfo) -> bool:
    return False

  @property
  def enabled(self) -> bool:
    return True

  def readKey(self, timeout: float = 0.0):
    # 待機を伴う読み出しのときだけキーを返す（即時ポーリングでは何も返さない）
    if timeout <= 0:
      return None
    # キーを使い切った場合は，テストが止まらないよう終了キーを返す
    key = self.keys.pop(0) if self.keys else "q"
    self.pressedKeys.append(key)
    return key


def test_pausedPlaybackStillAcceptsKeys(sampleVideo, monkeypatch):
  """一時停止中のキー入力が取りこぼされないことを確認する."""
  import fraterm.player as playerModule

  scriptedReader = ScriptedKeyReader([" ", "q"])
  monkeypatch.setattr(playerModule, "KeyReader", lambda: scriptedReader)

  player = Player(sampleVideo, PlaybackOptions(width=20), stream=io.StringIO())
  player.play()

  assert scriptedReader.pressedKeys == [" ", "q"]
  assert player._paused is True


def test_restartKeyReturnsToBeginning(sampleVideo, monkeypatch):
  """r キーで再生位置が先頭へ戻ることを確認する."""
  import fraterm.player as playerModule

  scriptedReader = ScriptedKeyReader(["r", "q"])
  monkeypatch.setattr(playerModule, "KeyReader", lambda: scriptedReader)

  player = Player(sampleVideo, PlaybackOptions(width=20), stream=io.StringIO())
  player.play()

  assert player._nextFrameIndex <= 1
  assert player._mediaBase == 0.0


@pytest.mark.parametrize(
  "speed, expectedFilterCount",
  [(1.5, 1), (3.0, 2), (0.25, 2)],
)
def test_buildTempoFilter(speed, expectedFilterCount):
  """再生速度に応じた atempo フィルタが組み立てられることを確認する."""
  filterText = audio.buildTempoFilter(speed)
  assert filterText.count("atempo=") == expectedFilterCount


def test_buildTempoFilterKeepsTotalSpeed():
  """連結した atempo の積が指定速度と一致することを確認する."""
  filterText = audio.buildTempoFilter(4.0)
  total = 1.0
  for part in filterText.split(","):
    total *= float(part.split("=")[1])
  assert total == pytest.approx(4.0, rel=1e-3)
