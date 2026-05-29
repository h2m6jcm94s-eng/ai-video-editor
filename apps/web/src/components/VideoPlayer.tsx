"use client";

import { useRef, useState } from "react";
import { Play, Pause, Volume2, VolumeX, Download, Share2 } from "lucide-react";

interface Props {
  src: string;
}

export function VideoPlayer({ src }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const toggleMute = () => {
    if (videoRef.current) {
      videoRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setProgress(
        (videoRef.current.currentTime / videoRef.current.duration) * 100
      );
    }
  };

  return (
    <div className="space-y-4">
      <div className="relative aspect-video bg-slate-900 rounded-lg overflow-hidden">
        <video
          ref={videoRef}
          src={src}
          className="w-full h-full"
          onTimeUpdate={handleTimeUpdate}
          onEnded={() => setIsPlaying(false)}
          onError={() => setError("Failed to load video")}
        />
        {!isPlaying && !error && (
          <button
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center bg-black/30 hover:bg-black/40 transition"
          >
            <Play className="w-16 h-16 text-white opacity-90" />
          </button>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60">
            <p className="text-white text-sm">{error}</p>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="space-y-2">
        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-indigo-500 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <button
              onClick={togglePlay}
              className="p-2 rounded-lg hover:bg-slate-100 transition"
            >
              {isPlaying ? (
                <Pause className="w-5 h-5 text-slate-700" />
              ) : (
                <Play className="w-5 h-5 text-slate-700" />
              )}
            </button>
            <button
              onClick={toggleMute}
              className="p-2 rounded-lg hover:bg-slate-100 transition"
            >
              {isMuted ? (
                <VolumeX className="w-5 h-5 text-slate-700" />
              ) : (
                <Volume2 className="w-5 h-5 text-slate-700" />
              )}
            </button>
          </div>

          <div className="flex items-center space-x-2">
            <button className="flex items-center space-x-1 px-3 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition">
              <Share2 className="w-4 h-4" />
              <span>Share</span>
            </button>
            <button className="flex items-center space-x-1 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 transition">
              <Download className="w-4 h-4" />
              <span>Download</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
