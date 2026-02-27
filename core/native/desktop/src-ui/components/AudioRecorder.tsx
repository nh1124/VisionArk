import React, { useState, useRef } from "react"
import { Mic, Square, Trash2, Volume2 } from "lucide-react"

interface AudioRecorderProps {
    onRecordingComplete: (audioBlob: Blob) => void
    onCancel: () => void
}

export default function AudioRecorder({ onRecordingComplete, onCancel }: AudioRecorderProps) {
    const [isRecording, setIsRecording] = useState(false)
    const [recordingTime, setRecordingTime] = useState(0)
    const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
    const mediaRecorderRef = useRef<MediaRecorder | null>(null)
    const chunksRef = useRef<Blob[]>([])
    const timerRef = useRef<number | null>(null)

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            const mediaRecorder = new MediaRecorder(stream)
            mediaRecorderRef.current = mediaRecorder
            chunksRef.current = []

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    chunksRef.current.push(e.data)
                }
            }

            mediaRecorder.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: "audio/webm" })
                setAudioBlob(blob)
                stream.getTracks().forEach((track) => track.stop())
            }

            mediaRecorder.start()
            setIsRecording(true)
            setRecordingTime(0)
            timerRef.current = window.setInterval(() => {
                setRecordingTime((prev) => prev + 1)
            }, 1000)
        } catch (err) {
            console.error("Failed to start recording:", err)
            alert("Could not access microphone.")
        }
    }

    const stopRecording = () => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop()
            setIsRecording(false)
            if (timerRef.current) {
                window.clearInterval(timerRef.current)
                timerRef.current = null
            }
        }
    }

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60)
        const secs = seconds % 60
        return `${mins}:${secs.toString().padStart(2, "0")}`
    }

    const handleSave = () => {
        if (audioBlob) {
            onRecordingComplete(audioBlob)
        }
    }

    return (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 flex items-center justify-between gap-4 shadow-xl">
            {audioBlob ? (
                <>
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-cyan-500/20 rounded-full flex items-center justify-center text-cyan-500">
                            <Volume2 size={20} />
                        </div>
                        <div>
                            <p className="text-xs font-bold text-white uppercase tracking-wider">
                                Recording Ready
                            </p>
                            <p className="text-[10px] text-gray-500 font-mono">
                                {formatTime(recordingTime)}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={onCancel}
                            className="p-2 text-gray-500 hover:text-white transition-colors"
                        >
                            <Trash2 size={18} />
                        </button>
                        <button
                            onClick={handleSave}
                            className="bg-cyan-500 hover:bg-cyan-400 text-black px-4 py-2 rounded-xl text-xs font-bold transition-all active:scale-95"
                        >
                            Save Action
                        </button>
                    </div>
                </>
            ) : (
                <>
                    <div className="flex items-center gap-3">
                        <div
                            className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${isRecording ? "bg-red-500 animate-pulse" : "bg-gray-800"
                                }`}
                        >
                            <Mic
                                size={20}
                                className={isRecording ? "text-white" : "text-gray-500"}
                            />
                        </div>
                        <div>
                            <p className="text-xs font-bold text-white uppercase tracking-wider">
                                {isRecording ? "Recording..." : "Ready to record"}
                            </p>
                            <p
                                className={`text-[10px] font-mono ${isRecording ? "text-red-400" : "text-gray-500"
                                    }`}
                            >
                                {formatTime(recordingTime)}
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        {!isRecording ? (
                            <>
                                <button
                                    onClick={onCancel}
                                    className="p-2 text-gray-500 hover:text-white transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={startRecording}
                                    className="bg-white text-black hover:bg-gray-200 px-4 py-2 rounded-xl text-xs font-bold transition-all active:scale-95"
                                >
                                    Start
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={stopRecording}
                                className="bg-red-500 hover:bg-red-400 text-white px-4 py-2 rounded-xl text-xs font-bold transition-all active:scale-95 flex items-center gap-2"
                            >
                                <Square size={14} /> Stop
                            </button>
                        )}
                    </div>
                </>
            )}
        </div>
    )
}
