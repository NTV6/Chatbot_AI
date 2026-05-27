import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type Conversation = {
  id: number;
  title: string;
};

function App() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConv, setCurrentConv] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    const savedFiles = localStorage.getItem("uploadedFiles");
    return savedFiles ? JSON.parse(savedFiles) : [];
  });
  console.log("🚀 ~ App ~ uploadedFiles:", uploadedFiles)

  const bottomRef = useRef<HTMLDivElement>(null);

  const fetchConversations = async () => {
    const res = await fetch("http://localhost:8000/conversations");
    const data = await res.json();
    setConversations(data);
  };

  const loadMessages = async (id: number) => {
    setCurrentConv(id);

    const res = await fetch(`http://localhost:8000/conversations/${id}/messages`);
    const data = await res.json();
    setMessages(data);
  };

  const createNewChat = async () => {
    const res = await fetch("http://localhost:8000/conversations", {
      method: "POST",
    });

    const data = await res.json();
    fetchConversations();
    setCurrentConv(data.id);
    setMessages([]);
  };

  const handleAsk = async () => {
    if (!question.trim()) return;

    let convId = currentConv;

    if (!convId) {
      const res = await fetch("http://localhost:8000/conversations", {
        method: "POST",
      });

      const data = await res.json();
      convId = data.id;

      setCurrentConv(convId);
      fetchConversations();
    }

    const userMessage: Message = { role: "user", content: question };
    setMessages((prev) => [...prev, userMessage]);

    setLoading(true);
    const currentQuestion = question;
    setQuestion("");

    try {
      const res = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_id: convId,
          question: currentQuestion,
        }),
      });

      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer },
      ]);

      fetchConversations();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadFile = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(
        "http://localhost:8000/upload_file",
        {
          method: "POST",
          body: formData,
        }
      );
      const data = await res.json();
      if (!res.ok) {
        setUploadResult(
          data.detail || "Upload thất bại"
        );
        return;
      }
      setUploadResult(
        `Upload thành công: ${data.file}`
      );
      setUploadedFiles((prev) => {
        if (prev.includes(data.file)) return prev; // Không thêm nếu đã có
        const updated = [...prev, data.file];
        localStorage.setItem("uploadedFiles", JSON.stringify(updated));
        return updated;
      });
    } catch (err) {
      console.error(err);
      setUploadResult(
        "Lỗi kết nối tới server"
      );
    } finally {
      setUploading(false);
      // reset input
      e.target.value = "";
    }
  };

  // Xóa file đã upload
  const handleDeleteFile = async (fileToDelete: string) => {
    // Gọi API backend để xóa file vật lý
    try {
      await fetch(`http://localhost:8000/delete_file`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ filename: fileToDelete }),
      });
    } catch (err) {
      console.error("Lỗi khi xóa file trên server:", err);
    }
    const updatedFiles = uploadedFiles.filter((file) => file !== fileToDelete);
    setUploadedFiles(updatedFiles);
    localStorage.setItem("uploadedFiles", JSON.stringify(updatedFiles));
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    document.title = "Chatbot AI";
    const fetchData = async () => {
      await fetchConversations();
    };
    fetchData();
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="w-64 bg-gray-200 p-4 overflow-y-auto flex-shrink-0">

        <h1 className="font-bold text-xl pb-2">AI Chat</h1>
        <button className="py-2 px-2 hover:bg-gray-300 rounded w-full text-left" onClick={createNewChat}>+ New Chat</button>

        <div className="flex flex-col items-start">

          <label
            className="py-2 px-2 hover:bg-gray-300 rounded w-full text-left font-semibold">
            + Tải lên file
            <input
              type="file"
              accept=".pdf,.docx,.xlsx"
              onChange={handleUploadFile}
              className="hidden"
            />
          </label>

          {uploading && (
            <div className="text-blue-500 text-sm my-2">
              Đang tải lên...
            </div>
          )}

          {uploadResult && (
            <div className="text-xs text-gray-700 my-2 whitespace-pre-line break-words max-w-xs">
              {uploadResult}
            </div>
          )}
        </div>

        <div>
          <p className="font-semibold my-2">
            File đã upload
          </p>

          <div className="space-y-2">
            {uploadedFiles.map((file, index) => (
              <div
                key={index}
                className="bg-white text-sm px-3 py-2 rounded-lg shadow break-words flex items-center justify-between"
              >
                <span>📄 {file}</span>
                <button
                  className="ml-2 text-gray-400 hover:text-red-500"
                  title="Xóa file"
                  onClick={() => handleDeleteFile(file)}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>

        <h2 className="font-bold py-2 pt-4">Gần đây</h2>

        {conversations.map((c) => (
          <div key={c.id} className="flex items-center group hover:bg-gray-300 rounded px-2 cursor-pointer">
            <div className="flex-1 py-2" onClick={() => loadMessages(c.id)}>
              {c.title}
            </div>
            <button
              className="ml-2 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition"
              title="Xóa đoạn chat"
              onClick={async (e) => {
                e.stopPropagation();
                await fetch(`http://localhost:8000/conversations/${c.id}`, {
                  method: "DELETE",
                });

                if (currentConv === c.id) {
                  setCurrentConv(null);
                  setMessages([]);
                }
                fetchConversations();
              }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto bg-gray-100">
          <div className="max-w-4xl mx-auto px-4 py-6 space-y-6 min-h-full">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center text-gray-500 h-[84vh]">
                <p className="text-2xl">Chào mừng bạn đến với AI Chat!</p>
                <p className="mt-2">Hãy bắt đầu bằng cách đặt câu hỏi cho AI.</p>
              </div>
            )}
            {messages.map((msg, index) => (
              <div
                key={index}
                className={`flex gap-3 items-end ${msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
              >
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center text-white text-sm">
                    AI
                  </div>
                )}

                <div
                  className={`
            max-w-[90%] px-4 py-3 rounded-2xl leading-relaxed
            ${msg.role === "user"
                      ? "bg-blue-500 text-white rounded-br-none"
                      : "bg-white text-gray-800 shadow rounded-bl-none"
                    }
          `}
                >
                  {
                    msg.role === "user" ? (
                      <div className="text-white whitespace-pre-wrap">
                        {msg.content}
                      </div>
                    ) : (
                      <div className="prose max-w-none">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    )
                  }
                </div>

                {msg.role === "user" && (
                  <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white text-sm">
                    U
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-3 items-end">
                <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center text-white text-sm">
                  AI
                </div>

                <div className="bg-white px-4 py-2 rounded-2xl shadow text-gray-500">
                  <span className="animate-pulse">...</span>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </div>

        <div className="p-4 bg-white border-t">
          <div className="max-w-3xl mx-auto flex gap-2 items-end">
            <textarea
              ref={textareaRef}
              rows={1}
              className="
    flex-1
    border
    rounded-xl
    px-4
    py-2
    resize-none
    max-h-40
    overflow-hidden
    focus:outline-none
    focus:ring-2
    focus:ring-blue-400
  "
              value={question}
              onChange={(e) => {
                setQuestion(e.target.value);

                const textarea = textareaRef.current;

                if (textarea) {
                  textarea.style.height = "auto";
                  textarea.style.height = textarea.scrollHeight + "px";
                }
              }}
              placeholder="Nhập câu hỏi..."
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleAsk();

                  // reset chiều cao sau khi gửi
                  if (textareaRef.current) {
                    textareaRef.current.style.height = "auto";
                  }
                }
              }}
            />

            <button
              onClick={handleAsk}
              disabled={loading}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white px-4 py-2 rounded-xl h-[40px] "
            >
              Gửi
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;