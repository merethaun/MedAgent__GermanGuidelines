import {useParams} from "react-router-dom";

export default function ChatInteractionPage() {
  const {chatId} = useParams();
  return (
    <div style={{padding: 16}}>
      <h2>Chat</h2>
      <p>Platzhalter Chat-ID: <b>{chatId}</b></p>
      <p>Platzhalter: später Messages + References + PDF Links.</p>
    </div>
  );
}
