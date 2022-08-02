%%
clear
close all
format compact
format short e
addpath(...
    'classes',...
    'builders',...
    'PuncturedDomainHigherOrderQuadrature',...
    'LocalLinearSystem')
tic

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% control center
%{
    redo: 
        if true, recomputes all quantities;
        otherwise, pulls data from files whenever possible
    save_figs:
        if true, saves all open figures to .pdf format at end of execution
    plot_{thing}:
        if true, plots {thing}
%}

redo = false; 
redo_intval = false;
redo_local_system = false;

save_figs = false;
plot_element = false;
plot_mesh = false;
plot_traces = false;
plot_local_basis = false;
plot_solution = true;

%% finite element formulation for landscape function
%{
    The weak formulation is given by 
        B(u,v) = F(v) for all v in V,
    where 
        B(u,v) = -a*(Laplacian u) + c*u     for constants a,c,
        F(v) = f*v                          for polynomial f.
    The finite element system is given by 
        B(A,M)*u = b
    where 
        B(A,M) = a*A+b*M, A stiffness matrix, M mass matrix,
        b_i = \int_K f*v_i dx, v_i is a basis function.
    
    do_L2: 
        if true, the local mass matrix is computed;
        otherwise, M is populated with NaNs.
    do_H1: 
        if true, the local stiffness matrix is computed;
        otherwise, A is populated with NaNs.
%}
B = @(Amat,Mmat) Amat;
do_L2 = false;
do_H1 = true;

%% right-hand side: constant function f = 1
f = class_poly();
f = f.constant(1);

%% mesh cell parameters
elm_args.id = 'square-circular-hole';
elm_args.r_in = 0.25;

%% global mesh parameters
mesh_args.r = 2;          % r x r mesh on the unit square 

%% function space parameters
funsp_args.deg = 1; % polynomial degree, V_m(K)

%% Dirichlet-to-Neumann map parameters
d2n_args.type = 'density';
d2n_args.restart = 10;
d2n_args.tol = 1e-12;
d2n_args.maxit = 5;

%% quadrature parameters
quad_args.n = 128;        % 2n points sampled per edge
quad_args.kress_sig = 7;  % Kress quadrature parameter \sigma > 2

%% local interior value parameters (for plotting)
intval_args.n_x = 64;
intval_args.n_y = intval_args.n_x;
intval_args.tol = 0.01;


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
%% file management
[filename,make_new] = file_management(elm_args.id,funsp_args.deg,redo);

%% build quadrature
quad = BuildQuads(quad_args);
for q = 1:3
    disp(quad{q})
end

%% build element K
elm = BuildElement(elm_args,quad);
disp(elm)

%% plot element boundary
if plot_element
    figure(1),clf
    elm.plot_boundary('quiver')
end

%% generate a basis of V_m(K)
vmk = class_local_function_space;
vmk = vmk.init(elm,quad,funsp_args);
disp(vmk)

%% plot local basis traces
if plot_traces
    vmk.print(101,elm,quad)
end

%% set up local interior grid points (for basis function plots)
intval_args.num_funcs = vmk.dim;
intval = class_interior_values;
intval = intval.init(elm,intval_args);

%% find points in interior
if make_new.intptsx || make_new.intptsy || redo_intval
    % get coordinates
    intval = intval.get_physical_pts(elm);
    % save to file
    dlmwrite(filename.intptsx,intval.x);
    dlmwrite(filename.intptsy,intval.y);
else
    disp('Loading coordinates of interior points from file...');
    % load from file
    intval.x = dlmread(filename.intptsx);
    intval.y = dlmread(filename.intptsy);
    % get array sizes, determine points inside element
    intval = intval.set_sizes();
    intval.in = intval.is_inside(elm);
end

%% get interior values of basis functions
if make_new.intval || redo_intval
    % get values
    intval = intval.get_int_vals(vmk,elm,quad,d2n_args);
    % save to file
    dlmwrite(filename.intval,intval.val);
else
    disp('Loading interior values from file...');
    % load from file
    intval.val = dlmread(filename.intval);
end

disp(intval)

%% contour plots of local basis functions
if plot_local_basis
    % show points where the functions will be evaluated
    figure(200),clf
    intval.show_points(elm);
    % make contour plots
    fig_type = 'contour';
    intval.plot_all(201,elm,fig_type)
end

%% compute local stiffness/mass matrices
if make_new.lsm || make_new.lmm || redo_local_system
    % get matrices
    [A,M] = LocalStiffnessMassMatrices(vmk,elm,quad,d2n_args,do_L2,do_H1);
    % save to file
    dlmwrite(filename.lsm,A);
    dlmwrite(filename.lmm,M);
else
    disp('Loading local stiffness and mass matrices from file...');
    % load from file
    A = dlmread(filename.lsm);
    M = dlmread(filename.lmm);
end

%% compute right-hand side
if make_new.rhs_h1 || make_new.rhs_l2
    % compute RHS
    [a,m] = LocalRHS(vmk,elm,quad,f,d2n_args);
    % save to file 
    dlmwrite(filename.rhs_h1,a);
    dlmwrite(filename.rhs_l2,m);
else
    disp('Loading local right-hand sides from file...');
    % load from file
    a = dlmread(filename.rhs_h1);
    m = dlmread(filename.rhs_l2);
end

%% construct mesh 
mesh = class_uniform_mesh_square_domain;
mesh = mesh.init(mesh_args.r,elm,vmk);
disp(mesh)

coef = zeros(mesh.num_glob_funs,1);
coef(3) = 1;

%% plot global solution
if plot_solution
    fig_type = 'contour';
    figure(99)
    mesh.plot_linear_combo(intval,coef,fig_type);
    hold on
    mesh.draw(elm)
    hold off
end



%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% exit by displaying elapsed time
disp('done!')
toc

%% file management
function [filename,make_new] = file_management(elm_id,vmk_deg,redo)

    % file names
    filename.lsm = sprintf(...
        'data-linear-system/%s-m%d-lsm.dat',elm_id,vmk_deg);
    filename.lmm = sprintf(...
        'data-linear-system/%s-m%d-lmm.dat',elm_id,vmk_deg);
    filename.rhs_h1 = sprintf(...
        'data-linear-system/%s-m%d-rhs-h1.dat',elm_id,vmk_deg);
    filename.rhs_l2 = sprintf(...
        'data-linear-system/%s-m%d-rhs-l2.dat',elm_id,vmk_deg);
    filename.intptsx = sprintf(...
        'data-plots/%s-intptsx.dat',elm_id);
    filename.intptsy = sprintf(...
        'data-plots/%s-intptsy.dat',elm_id);
    filename.intval = sprintf(...
        'data-plots/%s-m%d-intval.dat',elm_id,vmk_deg);
    
    if redo
        make_new.lsm = true;
        make_new.lmm = true;
        make_new.rhs_h1 = true;
        make_new.rhs_l2 = true;
        make_new.intptsx = true;
        make_new.intptsy = true;
        make_new.intval = true;
    else
        % mark which quantities need to be computed
        make_new.lsm = ~( exist(filename.lsm,'file') == 2 );
        make_new.lmm = ~( exist(filename.lmm,'file') == 2 );
        make_new.rhs_h1 = ~( exist(filename.rhs_h1,'file') == 2 );
        make_new.rhs_l2 = ~( exist(filename.rhs_l2,'file') == 2 );
        make_new.intptsx = ~( exist(filename.intptsx,'file') == 2 );
        make_new.intptsy = ~( exist(filename.intptsy,'file') == 2 );
        make_new.intval = ~( exist(filename.intval,'file') == 2 );
    end
    
end

%%
function save_all_figs(filename_format)

    fprintf('Saving figures to: %s\n',filename_format);

    figHandles = findobj('Type', 'figure');
    for i = 1:numel(figHandles)
        fig_num = figHandles(i).Number;
        % Position the plot further to the left and down. 
        % Extend the plot to fill entire paper.
        set(figHandles(i), 'PaperPosition', [-0.5 -0.25 6 5.5]); 
        % Keep the same paper size
        set(figHandles(i), 'PaperSize', [5 5]); 
        filename = sprintf(filename_format,fig_num);
        saveas(figHandles(i),filename,'pdf');
    end
    
end
