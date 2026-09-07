// socket to backend
const ws = new WebSocket("ws://127.0.0.1:9001/ws");

// dom refs
const connectButton = document.getElementById("connect-button")
const disconnectButton = document.getElementById("disconnect-button");
const connectionSection = document.getElementById("connection");
const chatSection = document.getElementById("chat");
const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const messages = document.getElementById("messages");

const mockMessages = [
    {
        sender: "other",
        text: "hi"
    },
    {
        sender: "me",
        text: "what's up?"
    },
    {
        sender: "other",
        text: "good and u?"
    }
];

let msgs = []
msgs.push(...mockMessages)

/* ==========
*  LISTNERS
*  ==========
*/ 

// listener for connect btn
connectButton.addEventListener("click", function () {
    ws.send(JSON.stringify({ type: "CONNECT" }));
});

// listener for disconnect btn
disconnectButton.addEventListener("click", function () {
    ws.send(JSON.stringify({ type: "DISCONNECT" }));

    connectionSection.hidden = false
    chatSection.hidden = true
});

// listener for backend events
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
        case "CONNECTED":
            connected();
            break;
        case "DISCONNECTED":
            disconnected();
            break;
        case "MESSAGE_RECEIVED":
            message_received(data.text);
            break;
        case "ERROR":
            error(data.reason);
            break;
    }
};

/* =============
*  UI FUNCTIONS
*  =============
*/ 

/*
 * show empty msgs page
 * show msg saying connected
 */
function connected() {
    connectionSection.hidden = true
    chatSection.hidden = false

    updateChat()
}

function updateChat() {
    const messages = document.getElementById("messages");

    messages.replaceChildren();

    for (const message of msgs) {
        const element = document.createElement("div");

        element.textContent = message.text;

        if (message.sender === "me") {
            element.className = "message message-own";
        } else {
            element.className = "message message-other";
        }

        messages.appendChild(element);
    }
}

/*
 * show text on the left side 
 */
function message_received(text) {
    msgs.push({ sender: 'other', text: text });
    updateChat();
}

/*
 * go back to disconnected page 
*/
function disconnected() {
    msgs = []
    connectionSection.hidden = false;
    chatSection.hidden = true;

}

/*
* show error msg on screen 
*/
function error(reason) {
    alert(reason)
}

messageForm.addEventListener("submit", (event) => {
    event.preventDefault();

    message = messageInput.value;

    if (!message) return;

    msgs.push({
        sender: "me",
        text: message
    });

    ws.send(JSON.stringify({
        type: "SEND_MESSAGE",
        text: message
    }));

    messageInput.value = "";

    updateChat();
});