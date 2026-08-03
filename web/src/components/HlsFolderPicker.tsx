import { useEffect, useRef } from "react";
import { FolderOpen, SpinnerGap } from "@phosphor-icons/react";

interface Props {
  compact?: boolean;
  disabled?: boolean;
  busy?: boolean;
  onFiles: (files: File[]) => void;
}

export function HlsFolderPicker({ compact = false, disabled = false, busy = false, onFiles }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const label = busy ? "正在上传文件夹" : compact ? "添加 M3U8" : "选择 M3U8 文件夹";

  useEffect(() => {
    inputRef.current?.setAttribute("webkitdirectory", "");
    inputRef.current?.setAttribute("directory", "");
  }, []);

  return (
    <>
      <button
        className={`button button-secondary${compact ? "" : " hls-picker-button"}`}
        type="button"
        disabled={disabled || busy}
        aria-label={label}
        onClick={() => inputRef.current?.click()}
      >
        {busy
          ? <SpinnerGap className="spin" size={18} aria-hidden="true" />
          : <FolderOpen size={18} aria-hidden="true" />}
        <span>{label}</span>
      </button>
      <input
        ref={inputRef}
        className="visually-hidden"
        type="file"
        name="hls-directory"
        multiple
        autoComplete="off"
        disabled={disabled || busy}
        aria-label="选择 M3U8 文件夹"
        onChange={(event) => {
          if (event.target.files?.length) onFiles(Array.from(event.target.files));
          event.target.value = "";
        }}
      />
    </>
  );
}
