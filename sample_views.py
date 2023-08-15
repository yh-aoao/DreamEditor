import argparse
import tqdm
import os
import cv2
import torch
import numpy as np
from nerf.provider import SampleViewsDataset
from nerf.provider_utils import seed_everything
from nerf.utils_init_nerf import Trainer_Nerf


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--text', default=None, help="text prompt")
    parser.add_argument('--negative', default='', type=str, help="negative text prompt")
    parser.add_argument('-O', action='store_true', help="equals --fp16 --cuda_ray --dir_text")
    parser.add_argument('-O2', action='store_true', help="equals --fp16 --dir_text")
    parser.add_argument('--test', action='store_true', help="test mode")
    parser.add_argument('--save_mesh', action='store_true', help="export an obj mesh with texture")
    parser.add_argument('--eval_interval', type=int, default=50, help="evaluate on the valid set every interval epochs")
    parser.add_argument('--workspace', type=str, default='workspace')
    parser.add_argument('--guidance', type=str, default='stable-diffusion', help='choose from [stable-diffusion, clip]')
    parser.add_argument('--seed', type=int, default=0)

    ### training options
    parser.add_argument('--iters', type=int, default=1200000, help="training iters")
    parser.add_argument('--lr', type=float, default=5e-4, help="initial learning rate")
    parser.add_argument('--ckpt', type=str, default='latest')
    parser.add_argument('--cuda_ray', action='store_true', help="use CUDA raymarching instead of pytorch")
    parser.add_argument('--max_steps', type=int, default=1024,
                        help="max num steps sampled per ray (only valid when using --cuda_ray)")
    parser.add_argument('--num_steps', type=int, default=64,
                        help="num steps sampled per ray (only valid when not using --cuda_ray)")
    parser.add_argument('--upsample_steps', type=int, default=64,
                        help="num steps up-sampled per ray (only valid when not using --cuda_ray)")
    parser.add_argument('--update_extra_interval', type=int, default=16,
                        help="iter interval to update extra status (only valid when using --cuda_ray)")
    parser.add_argument('--max_ray_batch', type=int, default=4096,
                        help="batch size of rays at inference to avoid OOM (only valid when not using --cuda_ray)")
    parser.add_argument('--albedo_iters', type=int, default=300000, help="training iters that only use albedo shading")
    parser.add_argument('--learn_vector', type=bool, default=False,
                        help="training iters that only use albedo shading")
    # model options
    parser.add_argument('--bg_radius', type=float, default=0.,
                        help="if positive, use a background model at sphere(bg_radius)")
    parser.add_argument('--bg_nerf', type=float, default=-1,
                        help="if positive, use a background model at sphere(bg_radius)")
    parser.add_argument('--teacher_path', type=str, default='./res/grid_sdf/df_nomask.pth')
    parser.add_argument('--prenet_path', type=str, default=None)
    parser.add_argument('--far_point_thresh', type=float, default=0.05,
                        help="if positive, use a background model at sphere(bg_radius)")
    parser.add_argument('--bg_black', type=bool, default=False)
    parser.add_argument('--bg_white', type=bool, default=False)
    parser.add_argument('--bg_color', type=float, nargs='*', default=None)
    parser.add_argument('--density_thresh', type=float, default=10, help="threshold for density grid to be occupied")
    # network backbone
    parser.add_argument('--K', type=int, default=8, help="GUI width")
    parser.add_argument('--fp16', action='store_true', help="use amp mixed precision training")
    parser.add_argument('--prior_mesh', type=str, default='./mesh_sdf/doll_sdf_g_30k.ply')
    parser.add_argument('--color_dim', type=int, default=128, help="GUI height")
    parser.add_argument('--geometry_dim', type=int, default=128, help="GUI width")
    parser.add_argument('--color_en', type=bool, default=False, help="GUI height")
    parser.add_argument('--geometry_en', type=bool, default=False, help="GUI width")
    parser.add_argument('--sigma_net_d', type=int, default=2, help="GUI width")
    parser.add_argument('--sigma_net_w', type=int, default=256, help="GUI height")
    parser.add_argument('--color_net_d', type=int, default=3, help="GUI width")
    parser.add_argument('--color_net_w', type=int, default=256, help="GUI height")
    parser.add_argument('--backbone', type=str, default='mesh_neus',
                        help="nerf backbone, choose from [neus, mesh_neus, grid, vanilla]")
    parser.add_argument('--pts_en', type=str, default='tiledgrid',
                        help="nerf backbone, choose from [mesh, grid, vanilla]")
    parser.add_argument("--if_direction", type=bool, default=True)
    parser.add_argument("--if_data_cuda", type=bool, default=True)
    parser.add_argument("--if_gt_depth", type=bool, default=False)
    parser.add_argument("--if_gt_sdf", type=bool, default=False)
    parser.add_argument("--if_mask", type=bool, default=False)
    parser.add_argument("--if_smooth", type=bool, default=False)
    parser.add_argument("--if_bg_model", type=bool, default=False)
    parser.add_argument("--fine_sigma_net", type=bool, default=False)
    parser.add_argument("--fine_ln", type=bool, default=False)
    parser.add_argument("--fine_color_net", type=bool, default=False)
    # rendering resolution in training, decrease this if CUDA OOM.
    parser.add_argument('--w', type=int, default=400, help="render width for NeRF in training")
    parser.add_argument('--h', type=int, default=300, help="render height for NeRF in training")
    parser.add_argument('--jitter_pose', action='store_true', help="add jitters to the randomly sampled camera poses")

    ### dataset options
    parser.add_argument("--data_path", type=str, default='/mnt/d/dataset/data_DTU/dtu_scan105/',
                        help='input data directory')
    parser.add_argument("--pose_sample_strategy", type=str, default='front_back',
                        help='input data directory')
    parser.add_argument("--data_type", type=str, default='dtu',
                        help='input da')
    parser.add_argument("--R_path", type=str, default=None,
                        help='input data directory')
    parser.add_argument("--sample_R_path", type=str, default=None,
                        help='input data directory')
    parser.add_argument("--if_sphere", type=bool, default=False)
    parser.add_argument("--pose_path", type=str, default=None,
                        help='input data directory')
    parser.add_argument('--batch_size', type=int, default=1, help="GUI width")
    parser.add_argument('--batch_rays', type=int, default=512, help="GUI width")
    parser.add_argument('--train_resolution_level', type=int, default=1, help="GUI width")
    parser.add_argument('--eval_resolution_level', type=int, default=4, help="GUI width")
    parser.add_argument('--num_work', type=int, default=0, help="GUI width")
    parser.add_argument("--train_white_bkgd", type=bool, default=True)
    parser.add_argument("--val_white_bkgd", type=bool, default=True)
    parser.add_argument('--train_batch_type', type=str, default='all_images')
    parser.add_argument('--val_batch_type', type=str, default='single_image')
    parser.add_argument('--bound', type=float, default=1.0, help="assume the scene is bounded in box(-bound, bound)")
    parser.add_argument('--dt_gamma', type=float, default=0,
                        help="dt_gamma (>=0) for adaptive ray marching. set to 0 to disable, >0 to accelerate rendering (but usually with worse quality)")
    parser.add_argument('--min_near', type=float, default=0.01, help="minimum near distance for camera")
    parser.add_argument('--radius_range', type=float, nargs='*', default=[0.2, 0.4],
                        help="training camera radius range")
    parser.add_argument('--fovy_range', type=float, nargs='*', default=[60, 80], help="training camera fovy range")
    parser.add_argument('--phi_list', type=float, nargs='*', default=[-180, 180], help="training camera fovy range")
    parser.add_argument('--theta_list', type=float, nargs='*', default=[0, 90], help="training camera fovy range")
    parser.add_argument('--dir_text', action='store_true',
                        help="direction-encode the text prompt, by appending front/side/back/overhead view")
    parser.add_argument('--negative_dir_text', action='store_true', help="also use negative dir text prompt.")
    parser.add_argument('--angle_overhead', type=float, default=30, help="[0, angle_overhead] is the overhead region")
    parser.add_argument('--angle_front', type=float, default=60,
                        help="[0, angle_front] is the front region, [180, 180+angle_front] the back region, otherwise the side region.")

    parser.add_argument('--lambda_eikonal', type=float, default=1e-1, help="loss scale for alpha entropy")
    parser.add_argument('--lambda_diss', type=float, default=1.0, help="loss scale for alpha entropy")
    parser.add_argument('--lambda_entropy', type=float, default=1e-4, help="loss scale for alpha entropy")
    parser.add_argument('--lambda_opacity', type=float, default=0, help="loss scale for alpha value")
    parser.add_argument('--lambda_orient', type=float, default=1e-2, help="loss scale for orientation")
    parser.add_argument('--lambda_smooth', type=float, default=0, help="loss scale for orientation")

    ### GUI options
    parser.add_argument('--gui', action='store_true', help="start a GUI")
    parser.add_argument('--W', type=int, default=400, help="GUI width")
    parser.add_argument('--H', type=int, default=300, help="GUI height")
    parser.add_argument('--radius', type=float, default=1, help="default GUI camera radius from center")
    parser.add_argument('--fovy', type=float, default=60, help="default GUI camera fovy")
    parser.add_argument('--light_theta', type=float, default=60,
                        help="default GUI light direction in [0, 180], corresponding to elevation [90, -90]")
    parser.add_argument('--light_phi', type=float, default=0, help="default GUI light direction in [0, 360), azimuth")
    parser.add_argument('--max_spp', type=int, default=1, help="GUI rendering max sample per pixel")

    opt = parser.parse_args()

    if opt.O:
        opt.fp16 = True
        opt.cuda_ray = True

    elif opt.O2:
        opt.fp16 = True

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


    if opt.backbone == 'grid':
        from nerf.network_grid import NeRFNetwork
    elif opt.backbone == 'neus':
        from nerf.network_neus import NeRFNetwork
    elif opt.backbone == 'mesh_neus':
        from nerf.network_mesh_neus import NeRFNetwork
    else:
        raise NotImplementedError(f'--backbone {opt.backbone} is not implemented!')


    seed_everything(opt.seed)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = NeRFNetwork(opt, device)

    print(model)

    trainer = Trainer_Nerf('df', opt, model, None, device=device, workspace=opt.workspace, fp16=opt.fp16, use_checkpoint=opt.ckpt)

    test_loader = SampleViewsDataset(opt, device=device, R_path=opt.R_path, type='test', H=512, W=512, size=100).dataloader()

    save_path = os.path.join(opt.workspace, 'sample_views')
    os.makedirs(save_path, exist_ok=True)

    with torch.no_grad():
        for i, data in tqdm.tqdm(enumerate(test_loader)):
            phi = int(data['phi'])
            theta = int(data['theta'])
            out_name = f'{theta}_{phi}.png'
            preds, preds_depth, dir = trainer.test_step(data, if_gui=True)
            pred = preds[0].detach().cpu().numpy()
            pred = (pred * 255).astype(np.uint8)
            cv2.imwrite(os.path.join(save_path, out_name),cv2.cvtColor(pred, cv2.COLOR_RGB2BGR))
