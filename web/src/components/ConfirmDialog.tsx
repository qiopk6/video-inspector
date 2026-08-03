import { useEffect, useRef } from "react";
import { Trash } from "@phosphor-icons/react";

interface Props {
  open: boolean;
  filename: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({ open, filename, onCancel, onConfirm }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="confirm-dialog" aria-labelledby="confirm-title" onCancel={onCancel} onClose={onCancel}>
      <div className="dialog-icon"><Trash size={24} aria-hidden="true" /></div>
      <h2 id="confirm-title">删除检测记录</h2>
      <p><strong>{filename}</strong> 的检测结果将从当前队列移除。</p>
      <div className="dialog-actions">
        <button className="button button-secondary" type="button" onClick={onCancel}>保留</button>
        <button className="button button-danger" type="button" onClick={onConfirm}>删除记录</button>
      </div>
    </dialog>
  );
}
