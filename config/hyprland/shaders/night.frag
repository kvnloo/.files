#version 300 es
// Night filter: independent blue-light reduction and software darkness.
// scripts/night-filter generates private runtime copies with persisted levels.
// At full blue-light reduction this retains the original red-light appearance.
precision highp float;

in vec2 v_texcoord;
uniform sampler2D tex;
out vec4 fragColor;

const float BLUE_LIGHT = 1.0;           // 0 = original color, 1 = full warm tint
const float DIM = 0.55;                 // 45% darkness; never below 10% via the CLI
const vec3 TINT = vec3(1.0, 0.38, 0.12);

void main() {
    vec4 c = texture(tex, v_texcoord);
    // Luma-preserving red: keep some detail in blue/green-only content.
    float luma = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    vec3 red = mix(c.rgb, vec3(luma), 0.35) * TINT;
    fragColor = vec4(mix(c.rgb, red, BLUE_LIGHT) * DIM, c.a);
}
