// Unified room unlock and chat functionality
async function handleRoomUnlock(roomId) {
    try {
        const response = await fetch('/unlock/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ room_id: roomId })
        });
        
        const data = await response.json();
        
        if (data.success && data.contact_details) {
            openChatInterface(roomId, data.contact_details.owner_name || 'Owner');
            return data;
        } else if (data.requires_payment) {
            openPaymentModal(roomId);
            return null;
        } else {
            alert('Error: ' + (data.error || 'Unable to unlock room'));
            return null;
        }
    } catch (error) {
        console.error('Error unlocking room:', error);
        alert('Error unlocking room. Please try again.');
        return null;
    }
}

// Preserve the dashboard-specific handler when one is already defined.
if (typeof window.handleRoomChat !== 'function') {
    window.handleRoomChat = handleRoomUnlock;
}

function getCsrfToken() {
    const cookie = document.cookie
        .split('; ')
        .find((row) => row.startsWith('csrftoken='));
    if (cookie) {
        return decodeURIComponent(cookie.substring('csrftoken='.length));
    }

    const tokenInput = Array.from(
        document.querySelectorAll('[name=csrfmiddlewaretoken]')
    ).find((input) => input.value && input.value.length === 64);
    return tokenInput ? tokenInput.value : '';
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}