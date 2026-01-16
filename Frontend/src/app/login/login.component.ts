import { Component, ElementRef, ViewChild, OnInit } from '@angular/core';
import { ChatService } from '../services/chat.service';

interface ChatMessage {
  text: string;
  isUser: boolean;
  type?: 'text' | 'image' | 'file';
  file?: File;
}

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent implements OnInit {
  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;
  showPassword: boolean = false;
  liveChat: boolean = false;
  expandChatWindow: boolean = false;

  // Chat properties
  messages: ChatMessage[] = [];
  userMessage: string = '';
  sessionId: string = '';
  prevRes: string | null = null;
  prevResMode: string | null = null;
  isLoading: boolean = false;

  togglePassword() {
    this.showPassword = !this.showPassword;
  }
  documents = [
    'Aadhaar Card',
    'Domicile Certificate',
    'Birth Certificate',
    'School Leaving Certificate',
    'Income Certificate',
    'Ration Card',
    'Voter ID',
    'Letter of Guarantee',
    'Bank Passbook',
    'Photograph'
  ];

  selectedDocType = '';

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  constructor(private chatService: ChatService) { }

  ngOnInit() {
    this.sessionId = this.generateSessionId();
    // specific initial greeting if needed, or wait for user interaction
    this.messages.push({
      text: "नमस्कार, मी महाराष्ट्र शासनाचा एजंटिक एआय सेवा बॉट आहे. मी तुमची लाडकी बहीण योजनेच्या माहितीसाठी आणि अर्जासाठी मदत करू शकतो. तुम्ही कशा प्रकारे मदत करू इच्छिता?",
      isUser: false
    });
    this.scrollToBottom();
  }

  generateSessionId(): string {
    return 'session_' + Math.random().toString(36).substr(2, 9);
  }

  openUploader(doc: string) {
    this.selectedDocType = doc;
    this.fileInput.nativeElement.click();
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;

    const file = input.files[0];

    console.log('Document Type:', this.selectedDocType);
    console.log('Uploaded File:', file);

    // Send file immediately as a message
    this.sendUserMessage(file);

    input.value = '';
  }
  openLiveChat() {
    this.liveChat = !this.liveChat;
  }
  toggleChatWindowSize() {
    this.expandChatWindow = !this.expandChatWindow;
  }

  sendUserMessage(file: File | null = null) {
    if (!this.userMessage.trim() && !file) return;

    let messageText = this.userMessage;
    if (file) {
      messageText = `Uploaded: ${file.name} (${this.selectedDocType})`;
    }

    // Add user message to UI
    this.messages.push({
      text: messageText,
      isUser: true,
      file: file || undefined
    });

    const currentMsg = this.userMessage; // Store for API call
    this.userMessage = ''; // Clear input
    this.isLoading = true;
    this.scrollToBottom();

    this.chatService.sendMessage(
      file ? "Uploaded document" : currentMsg,
      this.sessionId,
      this.prevRes,
      this.prevResMode,
      file,
      file ? this.selectedDocType : null
    ).subscribe({
      next: (res) => {
        this.isLoading = false;

        let botText = "";
        let responseObj = res.response;

        // If response is a string, try to parse it as JSON
        if (typeof responseObj === 'string') {
          try {
            // Check if it looks like a JSON object
            if (responseObj.trim().startsWith('{')) {
              const parsed = JSON.parse(responseObj);
              responseObj = parsed;
            }
          } catch (e) {
            // Not a JSON string, treat as raw text
          }
        }

        // Now handle the object (either originally an object or parsed from string)
        if (typeof responseObj === 'object' && responseObj !== null) {
          if (responseObj.message) {
            botText = responseObj.message;
          } else if (responseObj.response) {
            // specific case: { "response": "..." }
            botText = responseObj.response;

            // Recursive check: if the inner response is also a JSON string or object
            if (typeof botText === 'string') {
              try {
                if (botText.trim().startsWith('{')) {
                  const parsedInner = JSON.parse(botText);
                  if (parsedInner.message) {
                    botText = parsedInner.message;
                  }
                }
              } catch (e) { }
            } else if (typeof botText === 'object' && (botText as any).message) {
              botText = (botText as any).message;
            }

          } else {
            // Fallback: stringify the whole object if we interpret it as unknown structure
            // But typically we should have found 'message'
            botText = JSON.stringify(responseObj);
          }
        } else {
          // It's a primitive string
          botText = String(responseObj);
        }

        this.messages.push({
          text: botText,
          isUser: false
        });

        this.scrollToBottom();

        this.prevRes = botText;
        this.prevResMode = res.mode;
      },
      error: (err) => {
        this.isLoading = false;
        console.error('Chat error:', err);
        this.messages.push({
          text: "क्षमस्व, काहीतरी चूक झाली. कृपया पुन्हा प्रयत्न करा.",
          isUser: false
        });
        this.scrollToBottom();
      }
    });
  }

  handleQuickReply(reply: string) {
    this.userMessage = reply;
    this.sendUserMessage();
  }

  resetSession() {
    this.sessionId = this.generateSessionId();
    this.prevRes = null;
    this.prevResMode = null;
    this.messages = [];
    this.isLoading = false;

    // Add reset welcome message
    this.messages.push({
      text: "सत्र रीसेट. लाडकी बहिन योजनेबाबत मी तुम्हाला कशी मदत करू शकतो?",
      isUser: false
    });
    this.scrollToBottom();
  }

  scrollToBottom(): void {
    try {
      setTimeout(() => {
        this.scrollContainer.nativeElement.scrollTo({
          top: this.scrollContainer.nativeElement.scrollHeight,
          behavior: 'smooth'
        });
      }, 100);
    } catch (err) { }
  }

  currentAudio: HTMLAudioElement | null = null;
  isPlaying: boolean = false;

  playTextToSpeech(text: string) {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio = null;
      this.isPlaying = false;
    }

    // Strip markdown chars if any? for now simple text
    // The backend might need to handle cleaning if needed, but text usually comes clean or with simple formatting

    this.chatService.getAudio(text).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        this.currentAudio = new Audio(url);
        this.currentAudio.play();
        this.isPlaying = true;
        this.currentAudio.onended = () => {
          this.isPlaying = false;
          this.currentAudio = null;
        };
      },
      error: (err) => {
        console.error("Audio playback error", err);
      }
    });
  }
  formatMessage(text: string): string {
    if (!text) return '';
    let formatted = text;
    // Bold: **text** -> <b>text</b>
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
    // Newlines -> <br>
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
  }
}
