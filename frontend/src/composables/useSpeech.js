/**
 * 创新点 C：现场免手语音交互
 * - 语音输入：Web Speech API SpeechRecognition（中文识别 zh-CN）
 * - 语音播报：Web Speech API speechSynthesis（朗读检修步骤）
 *
 * 纯浏览器端实现，零后端依赖、零 LoongArch 架构风险（识别质量取决于浏览器，
 * Chrome/Edge 系最佳；不支持时优雅降级，按钮自动隐藏，仍可打字）。
 */
import { ref, onUnmounted } from 'vue'

export function useSpeech() {
  const SR = typeof window !== 'undefined'
    ? (window.SpeechRecognition || window.webkitSpeechRecognition)
    : null
  const recognitionSupported = ref(!!SR)
  const synthSupported = ref(typeof window !== 'undefined' && 'speechSynthesis' in window)

  const listening = ref(false)
  const speaking  = ref(false)
  let recog = null

  // ---------- 语音输入 ----------
  function startListening(onResult) {
    if (!SR) return
    try {
      recog = new SR()
      recog.lang = 'zh-CN'
      recog.interimResults = true
      recog.continuous = false
      let finalText = ''
      recog.onresult = (e) => {
        let interim = ''
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const tr = e.results[i][0].transcript
          if (e.results[i].isFinal) finalText += tr
          else interim += tr
        }
        onResult && onResult(finalText + interim, e.results[e.results.length - 1].isFinal)
      }
      recog.onerror = () => { listening.value = false }
      recog.onend   = () => { listening.value = false }
      recog.start()
      listening.value = true
    } catch {
      listening.value = false
    }
  }

  function stopListening() {
    try { recog && recog.stop() } catch { /* ignore */ }
    listening.value = false
  }

  // ---------- 语音播报 ----------
  function speak(text) {
    if (!synthSupported.value || !text) return
    try {
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(String(text))
      u.lang = 'zh-CN'
      u.rate = 1.0
      u.onstart = () => { speaking.value = true }
      u.onend   = () => { speaking.value = false }
      u.onerror = () => { speaking.value = false }
      window.speechSynthesis.speak(u)
    } catch {
      speaking.value = false
    }
  }

  function cancelSpeak() {
    try { window.speechSynthesis.cancel() } catch { /* ignore */ }
    speaking.value = false
  }

  onUnmounted(() => { stopListening(); cancelSpeak() })

  return {
    recognitionSupported, synthSupported,
    listening, speaking,
    startListening, stopListening,
    speak, cancelSpeak,
  }
}
