const parsedLimit = (raw: string | undefined, fallback: number) => {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
};

export const uploadPolicy = Object.freeze({
  maxFileSizeMb: parsedLimit(process.env.NEXT_PUBLIC_MAX_FILE_SIZE_MB, 10),
  maxFiles: parsedLimit(process.env.NEXT_PUBLIC_MAX_FILES_PER_REQUEST, 50),
  maxBatchSizeMb: parsedLimit(process.env.NEXT_PUBLIC_MAX_BATCH_SIZE_MB, 100),
});

export const supportedUploadExtensions = ["jpg", "jpeg", "png", "pdf", "zip"] as const;

function extensionOf(filename: string) {
  return filename.split(".").pop()?.toLowerCase() || "";
}

function startsWith(bytes: Uint8Array, signature: readonly number[]) {
  return signature.every((value, index) => bytes[index] === value);
}

function containsPdfHeader(bytes: Uint8Array) {
  const marker = [0x25, 0x50, 0x44, 0x46, 0x2d];
  for (let offset = 0; offset <= bytes.length - marker.length; offset += 1) {
    if (marker.every((value, index) => bytes[offset + index] === value)) return true;
  }
  return false;
}

function signatureMatches(extension: string, bytes: Uint8Array) {
  if (extension === "jpg" || extension === "jpeg") {
    return startsWith(bytes, [0xff, 0xd8, 0xff]);
  }
  if (extension === "png") {
    return startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  }
  if (extension === "pdf") return containsPdfHeader(bytes);
  if (extension === "zip") {
    return (
      startsWith(bytes, [0x50, 0x4b, 0x03, 0x04]) ||
      startsWith(bytes, [0x50, 0x4b, 0x05, 0x06]) ||
      startsWith(bytes, [0x50, 0x4b, 0x07, 0x08])
    );
  }
  return false;
}

export async function validateUploadFile(file: File): Promise<string | null> {
  const extension = extensionOf(file.name);
  if (!(supportedUploadExtensions as readonly string[]).includes(extension)) {
    return `${file.name}: unsupported file type`;
  }
  if (file.size === 0) return `${file.name}: the file is empty`;
  if (file.size > uploadPolicy.maxFileSizeMb * 1024 * 1024) {
    return `${file.name}: larger than ${uploadPolicy.maxFileSizeMb} MB`;
  }
  try {
    const bytes = new Uint8Array(await file.slice(0, 1024).arrayBuffer());
    if (!signatureMatches(extension, bytes)) {
      return `${file.name}: its contents do not match the .${extension} extension`;
    }
  } catch {
    return `${file.name}: the browser could not read this file`;
  }
  return null;
}

export function fileFingerprint(file: File) {
  return `${file.name.toLowerCase()}::${file.size}::${file.lastModified}`;
}
