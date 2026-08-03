import { useRef, useState } from "react";
import { FileVideo, UploadSimple } from "@phosphor-icons/react";

interface Props {
  compact?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}

const ACCEPT = ".mp4,.mov,.mkv,.avi,.wmv,.flv,.webm,.m4v,.mts,.m2ts,.ts,.mpg,.mpeg,.3gp,.vob,.mxf";

export function UploadDropzone({ compact = false, disabled = false, onFiles }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function takeFiles(list: FileList | null) {
    if (list?.length) onFiles(Array.from(list));
  }

  if (compact) {
    return (
      <>
        <button className="button button-primary" type="button" disabled={disabled} aria-label="添加视频" title="添加视频" onClick={() => inputRef.current?.click()}>
          <UploadSimple size={18} aria-hidden="true" />
          <span>添加视频</span>
        </button>
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          name="videos"
          accept={ACCEPT}
          multiple
          autoComplete="off"
          disabled={disabled}
          aria-label="选择视频文件"
          onChange={(event) => {
            takeFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </>
    );
  }

  return (
    <label
      className={`dropzone${dragging ? " is-dragging" : ""}${disabled ? " is-disabled" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (!disabled) takeFiles(event.dataTransfer.files);
      }}
    >
      <FileVideo size={34} weight="duotone" aria-hidden="true" />
      <span className="dropzone-title">放入待检测视频</span>
      <span className="dropzone-copy">拖放到这里，或点击选择多个文件</span>
      <input
        className="visually-hidden"
        type="file"
        name="videos-empty"
        accept={ACCEPT}
        multiple
        autoComplete="off"
        disabled={disabled}
        onChange={(event) => {
          takeFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </label>
  );
}
