export function wordCount(text: string) {
  const words = text.match(/[\p{L}\p{N}][\p{L}\p{N}\p{M}]*(?:['’\-][\p{L}\p{N}][\p{L}\p{N}\p{M}]*)*/gu);
  return words?.length ?? 0;
}

export async function readEssay(file: File) {
  if (file.size > 5 * 1024 * 1024) throw new Error("file");
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "txt" || extension === "md") return file.text();
  if (extension === "docx") {
    const mammoth = await import("mammoth/mammoth.browser");
    // Extract plain text locally. Embedded links and document HTML never enter the page.
    return (await mammoth.extractRawText({ arrayBuffer: await file.arrayBuffer() })).value;
  }
  throw new Error("file");
}
