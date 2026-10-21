#version 300 es
// Night filter: software dimming + red light. Toggled by scripts/night-filter.
// Keeps the red channel, cuts most green and nearly all blue (melatonin-friendly),
// then scales everything down because hardware brightness on these monitors is not
// software-controllable here.
precision highp float;

in vec2 v_texcoord;
uniform sampler2D tex;
out vec4 fragColor;

const float DIM = 0.55;                  // overall brightness multiplier
const vec3 TINT = vec3(1.0, 0.38, 0.12); // red light: R kept, G and B cut

void main() {
    vec4 c = texture(tex, v_texcoord);
    // Luma-preserving red: keep some detail in blue/green-only content.
    float luma = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    vec3 red = mix(c.rgb, vec3(luma), 0.35) * TINT;
    fragColor = vec4(red * DIM, c.a);
}
