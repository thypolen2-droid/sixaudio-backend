import re

class SSMLBuilder:
    def __init__(self, narrator_voice="en-US-AriaNeural", dialogue_voice="en-US-GuyNeural"):
        self.narrator_voice = narrator_voice
        self.dialogue_voice = dialogue_voice

    def build_ssml(self, text):
        """
        Parses text and applies SSML voice tags to dialogue vs narration.
        Dialogue is identified by "quotes" or “smart quotes”.
        """
        if not text:
            return ""

        # Normalize quotes to standard "
        text = text.replace('“', '"').replace('”', '"')
        
        # Split by quotes
        # This regex saves delimiters (quotes) so we can reconstruct the string
        parts = re.split(r'(".*?")', text)
        
        ssml_parts = []
        ssml_parts.append(f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">')
        
        for part in parts:
            if not part.strip():
                continue
                
            if part.startswith('"') and part.endswith('"'):
                # It's dialogue
                # Strip quotes for the audio? Usually keep them or not? 
                # Let's keep the content but maybe remove the literal quote marks to sound natural
                content = part[1:-1]
                if content.strip():
                    ssml_parts.append(f'<voice name="{self.dialogue_voice}">{content}</voice>')
            else:
                # It's narration
                ssml_parts.append(f'<voice name="{self.narrator_voice}">{part}</voice>')
                
        ssml_parts.append('</speak>')
        
        return "".join(ssml_parts)
