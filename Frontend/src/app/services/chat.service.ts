import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ChatResponse {
    response: string | any;
    mode: string;
}

@Injectable({
    providedIn: 'root'
})
export class ChatService {
    private apiUrl = 'http://localhost:9015/smart-chat-router-ladki-bahin';

    constructor(private http: HttpClient) { }

    sendMessage(
        message: string,
        sessionId: string,
        prevRes: string | null = null,
        prevResMode: string | null = null,
        file: File | null = null,
        docType: string | null = null
    ): Observable<ChatResponse | any> {
        const formData = new FormData();
        formData.append('message', message);
        formData.append('session_id', sessionId);

        if (prevRes) {
            formData.append('prev_res', prevRes);
        }

        if (prevResMode) {
            formData.append('prev_res_mode', prevResMode);
        }

        if (file) {
            formData.append('file', file);
        }

        if (docType) {
            formData.append('doc_type', docType);
        }

        return this.http.post<ChatResponse>(this.apiUrl, formData);
    }

    getAudio(text: string): Observable<Blob> {
        return this.http.post('http://localhost:9015/api/tts', { text: text }, {
            responseType: 'blob'
        });
    }
}
