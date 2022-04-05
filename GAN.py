#https://github.com/AquibPy/Enhanced-Super-Resolution-GAN/blob/main/model.py
import torch
import torch.nn as nn
from torch.nn.modules.linear import Linear

class ConvBlock(nn.Module):
    def __init__(self,in_channels, out_channels, use_act, **kwargs):
        super().__init__()
        self.cnn = nn.Conv2d(in_channels, out_channels, **kwargs, bias=True)
        self.act = nn.LeakyReLU(0.2, inplace=True) if use_act else nn.Identity()

    def forward(self,x):
        return self.act(self.cnn(x))

class UpsampleBlock(nn.Module):
    def __init__(self, in_channel, scale_factor = 2):
        super().__init__()
        self.upsample = nn.Upsample(scale_factor=scale_factor,mode="nearest")
        self.conv = nn.Conv2d(in_channel,in_channel,3,1,1,bias=True)
        self.act = nn.LeakyReLU(0.2, inplace=True)

    def forward(self,x):
        return self.act(self.conv(self.upsample(x)))

class DenseResidualBlock(nn.Module):
    def __init__(self, in_channels, channels = 32, residual_beta = 0.2):
        super().__init__()
        self.residual_beta = residual_beta
        self.blocks = nn.ModuleList()
        for i in range(5):
            self.blocks.append(
                ConvBlock(in_channels  + channels * i, channels if i<=3 else in_channels,
                kernel_size = 3,stride = 1, padding = 1, use_act=True if i<=3 else False)
            )

    def forward(self,x):
        new_inputs = x
        for block in self.blocks:
            out = block(new_inputs)
            new_inputs = torch.cat([new_inputs,out],dim = 1)
        return self.residual_beta * out + x


class RRDB(nn.Module):
    def __init__(self, in_channels, residual_beta = 0.2):
        super().__init__()
        self.residual_beta = residual_beta
        self.rrdb = nn.Sequential(*[DenseResidualBlock(in_channels) for _ in range(3)])

    def forward(self,x):
        return self.rrdb(x) * self.residual_beta + x

class Generator(nn.Module):
    def __init__(self, in_channels = 3, num_channels = 64, num_blocks = 23):
        super().__init__()
        self.initial = nn.Conv2d(in_channels,num_channels,kernel_size=3,stride=1,padding=1,bias=True)
        self.residuals = nn.Sequential(*[RRDB(num_channels) for _ in range(num_blocks)])
        self.conv = nn.Conv2d(num_channels,num_channels,kernel_size=3, stride=1, padding=1)
        self.upsamples = nn.Sequential(
            UpsampleBlock(num_channels), UpsampleBlock(num_channels),
        )
        self.final = nn.Sequential(
            nn.Conv2d(num_channels, num_channels, 3, 1, 1, bias=True),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(num_channels, in_channels, 3, 1, 1, bias=True),
        )

    def forward(self,x):
        initial = self.initial(x)
        x = self.residuals(initial)
        x = self.conv(x) + initial
        x = self.upsamples(x)
        return self.final(x)

class Discriminator(nn.Module):
    def __init__(self, in_channels=3, features=[64, 64, 128, 128, 256, 256, 512, 512]):
        super().__init__()
        blocks = []
        for idx, feature in enumerate(features):
            blocks.append(
                ConvBlock(
                    in_channels,
                    feature,
                    kernel_size=3,
                    stride=1 + idx % 2,
                    padding=1,
                    use_act=True,
                ),
            )
            in_channels = feature

        self.blocks = nn.Sequential(*blocks)
        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d((6, 6)),
            nn.Flatten(),
            nn.Linear(512 * 6 * 6, 1024),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(1024, 1),
        )

    def forward(self, x):
        x = self.blocks(x)
        return self.classifier(x)

def initialize_weights(model, scale=0.1):
    for m in model.modules():
        if isinstance(m , nn.Conv2d):
            nn.init.kaiming_normal_(m.weight.data)
            m.weight.data *= scale

        elif isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight.data)
            m.weight.data *= scale

def gradient_penalty(critic, real_hi_res, fake_hi_res, device):
    BATCH_SIZE, C, H, W = real_hi_res.shape
    alpha = torch.rand((BATCH_SIZE, 1, 1, 1)).repeat(1, C, H, W).to(device)
    interpolated_images = real_hi_res * alpha + fake_hi_res.detach() * (1 - alpha)
    interpolated_images.requires_grad_(True)

    # Calculate critic scores
    mixed_scores = critic(interpolated_images)

    # Take the gradient of the scores with respect to the images
    gradient = torch.autograd.grad(
        inputs=interpolated_images,
        outputs=mixed_scores,
        grad_outputs=torch.ones_like(mixed_scores),
        create_graph=True,
        retain_graph=True,
    )[0]
    gradient = gradient.view(gradient.shape[0], -1)
    gradient_norm = gradient.norm(2, dim=1)
    gradient_penalty = torch.mean((gradient_norm - 1) ** 2)
    return gradient_penalty

def test():
    low_resolution = 24  # 96x96 -> 24x24
    with torch.cuda.amp.autocast():
        x = torch.randn((5, 3, low_resolution, low_resolution))
        gen = Generator()
        gen_out = gen(x)
        disc = Discriminator()
        disc_out = disc(gen_out)

        print(gen_out.shape)
        print(disc_out.shape)
        # print(gen.parameters)
        # print(disc.parameters)

if __name__ == "__main__":
    test()
