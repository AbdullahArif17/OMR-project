"use client";

import { useEffect, useState, type FormEvent } from "react";
import { CloseIcon } from "@/components/icons";
import { Alert, Spinner } from "@/components/ui";
import type { Result } from "@/lib/types";

interface EditResultDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: { name: string | null; roll_number: string | null; class_name: string | null }) => Promise<void>;
  result: Result;
}

export function EditResultDialog({ isOpen, onClose, onSave, result }: EditResultDialogProps) {
  const [name, setName] = useState(result.student?.name || result.student_name || "");
  const [rollNumber, setRollNumber] = useState(result.student?.roll_number || result.roll_number || "");
  const [className, setClassName] = useState(result.student?.class_name || result.class_name || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Sync state if result changes while dialog is open or when it opens
  useEffect(() => {
    if (isOpen) {
      setName(result.student?.name || result.student_name || "");
      setRollNumber(result.student?.roll_number || result.roll_number || "");
      setClassName(result.student?.class_name || result.class_name || "");
      setError("");
    }
  }, [isOpen, result]);

  if (!isOpen) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      await onSave({
        name: name.trim() || null,
        roll_number: rollNumber.trim() || null,
        class_name: className.trim() || null,
      });
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to update result.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="animate-in fade-in zoom-in-95 surface-card w-full max-w-md p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-black text-slate-950">Edit Student Details</h2>
          <button className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600" onClick={onClose} type="button">
            <span className="sr-only">Close dialog</span>
            <CloseIcon size={20} />
          </button>
        </div>
        
        <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
          {error && <Alert>{error}</Alert>}
          
          <div>
            <label className="field-label" htmlFor="edit-name">Student Name</label>
            <input 
              className="text-field" 
              id="edit-name" 
              onChange={(e) => setName(e.target.value)} 
              placeholder="e.g. John Doe" 
              value={name} 
            />
          </div>
          
          <div>
            <label className="field-label" htmlFor="edit-roll">Roll Number</label>
            <input 
              className="text-field" 
              id="edit-roll" 
              onChange={(e) => setRollNumber(e.target.value)} 
              placeholder="e.g. 12345" 
              value={rollNumber} 
            />
          </div>
          
          <div>
            <label className="field-label" htmlFor="edit-class">Class</label>
            <input 
              className="text-field" 
              id="edit-class" 
              onChange={(e) => setClassName(e.target.value)} 
              placeholder="e.g. 10th Grade" 
              value={className} 
            />
          </div>
          
          <div className="mt-6 flex justify-end gap-3 border-t border-slate-100 pt-5">
            <button className="button-secondary" disabled={saving} onClick={onClose} type="button">Cancel</button>
            <button className="button-primary" disabled={saving} type="submit">
              {saving ? <><Spinner /> Saving…</> : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
