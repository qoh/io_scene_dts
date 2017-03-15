# FAQ

#### How do I export to a DTS file?

Go to `File -> Export -> Torque (.dts)` in the menu or press spacebar and search for `Export DTS` in the quick menu. The steps are the same for DSQ, only the operator is named `Export DSQ`.

#### How do I import from a DTS file?

Go to `File -> Import -> Torque (.dts)` in the menu or press spacebar and search for `Import DTS` in the quick menu. The steps are the same for DSQ, only the operator is named `Import DSQ`.

#### I have colored/textured materials on my model in Blender but the model appears white when I export it.

Torque uses texture files for materials that are looked up by the name of your material. For a material named "boxTrapOrange", you will need a PNG/JPG file with the same name. For solid colors (diffuse in Blender), you will need a texture as well. You will need to either create these yourself or use the option to generate colored textures on export.

#### My model is bigger/smaller, rotated wrong or in the wrong place when I export it.

Select your mesh and press `Ctrl-A` to apply location, rotation or scale. This will apply the mesh transforms to the actual geometry and clear them, which you need to do because DTS does not support them.

#### How do I make a material transparent?

Check the "Transparency" setting under material properties.

#### How do I make a material self illuminating?

Check the "Shadeless" setting under material properties.

#### How do I make a transparent material subtractive?

Add a custom property named "blendMode" and set it to "subtractive" in the material properties.

![](http://i.imgur.com/exQ5sqL.png)

![](http://i.imgur.com/FXufzLb.png)

#### How do I create IFL materials?

Set the following custom properties on the material:

* `iflName`
* `iflFirstFrame`
* `iflNumFrames`
* `iflTime`

I have yet to figure out how they work myself, so I can't quite document them yet.

#### How do I make a material refer to a different texture name than the material name?

Either use the # suffix (the name "foo#bar" would look for texture "foo") or set the custom property "texture".

#### My UV mapping is too small/big and doesn't even seem to loop.

Make sure your texture resolution is a power of 2 (..., 128, 256, 512, 1024, ...).

#### My UV mapping is distorted/shaped differently.

The exporter will automatically triangulate all meshes on export, and certain UV mappings you can do on quads (or n-gons) are impossible on triangles. Instead, triangulate the geometry yourself in Blender and do your UV mapping on that to get correct output.

#### What is the mesh size limit?

Right now you are limited to 21845 triangles. Explanation: You are limited to 65536 vertex indices and each face (triangle) uses three. `65536 / 3`.

#### What is the mesh number limit?

There is effectively no limit, but stay below 256 as anything higher sends invalid node update packets and will have random bad effects on clients.

#### How do I put a mesh in a detail level/LOD? How do detail levels work in this plugin?

The exporter will use the object group name as the detail level name if present. If your mesh is named "Col-X" it will put it in "Collision-X". Otherwise it uses "detail32" by default.

#### How do I create multiple LODs of the same node?

First of all, each LOD should be a separate mesh, and as stated in the previous question, set the object group name for each. Since Blender does not allow multiple objects with the same name, you will need to change the name.

For this reason the plugin ignores any part of a name after and including a # character. I recommend using something related to the LOD as the suffix. For example, `horn#32` and `horn#128` for an object named `horn` in `detail32` and `detail128`.

#### How do I add a collision mesh?

Add a mesh named "Col-X" where X is a number from 1 to 8(?). It must be in the "Collision-X" detail level, but the exporter will automatically do this for you based on the name.

#### How do I add a raycast collision mesh?

Add a mesh named "LOSCol-X" where X is a number from 9 to 16(?). It must be in the "LOS-X" detail level. The exporter should automatically do this for you but that hasn't been implemented yet.

#### Why are my collision meshes stopping players but not raycasts and projectiles?

I think it's because your mesh is concave instead of convex.

#### Can I tell the exporter to always ignore a mesh?

Set the object group name ('detail level') to "\_\_ignore\_\_".

#### How do I define the hierarchy of nodes for animations, mount points, muzzle points, etc.?

Ideally this is where the FAQ would just say "use bones", but this plugin does not support bones. It's basically the biggest remaining feature.

Regardless, create an empty for each node (visual type does not matter) and parent them to each other in Blender.

![](http://i.imgur.com/a89m7Hm.png)

#### How do I manually set the bounding box of my model?

Name one of your meshes "bounds".

#### Does this plugin care about layers?

No. It will export from every layer.

### When I import multiple animations they are messed up.

This is because the animations are "blending into each other", so to speak; the last keyframes of animations placed earlier in the timeline are staying and affecting later animations. A solution would have to be a root pose keyframe on every node inbetween animated animations, but the importer doesn't do this yet.

#### How do I define an animation?

Create a marker at the start frame and end frame of your animation on the timeline and name them appropriately: if your animation should be called "glide" then name them "glide:start" and "glide:end".

#### Can I use the different interpolation types for keyframe animations?

Yes.

#### How is the speed/duration of an animation determined?

It should have the same length in-game and in Blender. It will evaluate and export the animation at the scene FPS (24 by default).

#### How do I make an animation cyclic? How do I set the priority of an animations? How do I make an animation blend?

You need to create a text block (in the Text Editor view) named "Sequences" and list the properties of your animations. Here is an example of the format (in this case, the properties of the default player animations):

```
activate: priority 64, blend
activate2: priority 64, blend
armattack: priority 64, cyclic, blend
armreadyboth: priority 14
armreadyleft: priority 14
armreadyright: priority 14
back: priority 12, cyclic
crouch: priority 20
crouchback: priority 21, cyclic
crouchrun: priority 21, cyclic
crouchside: priority 21, cyclic
death1: priority 128
fall: priority 7
headside: priority 0, blend
headup: priority 0, blend
leftrecoil: priority 64, blend
look: priority 8, blend
plant: priority 64, blend
root: priority 0
rotccw: priority 64, blend
rotcw: priority 64, blend
run: priority 12, cyclic
shiftaway: priority 64, blend
shiftdown: priority 64, blend
shiftleft: priority 64, blend
shiftright: priority 64, blend
shiftto: priority 64, blend
shiftup: priority 64, blend
side: priority 12, cyclic
sit: priority 64
spearready: priority 14, blend
spearthrow: priority 14, blend
standjump: priority 8, blend
talk: priority 0, cyclic, blend
undo: priority 64, blend
wrench: priority 64, blend
```
